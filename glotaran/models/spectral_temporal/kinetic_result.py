import typing
import numpy as np
import xarray as xr

import glotaran
from glotaran.parameter import ParameterGroup

from .irf import IrfGaussian
from .spectral_constraints import OnlyConstraint, ZeroConstraint


def finalize_kinetic_data(
    model: 'glotaran.models.spectral_temporal.KineticModel',
    global_indices: typing.List[typing.List[object]],
    reduced_clp_labels: typing.Union[typing.Dict[str, typing.List[str]], np.ndarray],
    reduced_clps: typing.Union[typing.Dict[str, np.ndarray], np.ndarray],
    parameter: ParameterGroup, data: typing.Dict[str, xr.Dataset],
):

    for label in model.dataset:
        dataset = data[label]

        dataset_descriptor = model.dataset[label].fill(model, parameter)

        if not dataset_descriptor.get_k_matrices():
            continue

        compartments = dataset_descriptor.initial_concentration.compartments

        compartments = [c for c in compartments if c in dataset_descriptor.compartments()]
        # get_sas

        dataset.coords['species'] = compartments
        dataset['species_associated_spectra'] = \
            ((model.global_dimension, 'species',),
             dataset.clp.sel(clp_label=compartments))

        if dataset_descriptor.baseline:
            dataset['baseline'] = dataset.clp.sel(clp_label=f"{dataset_descriptor.label}_baseline")

        for constraint in model.spectral_constraints:
            if isinstance(constraint, (OnlyConstraint, ZeroConstraint)):
                idx = [index for index in dataset.spectral if constraint.applies(index)]
                if constraint.compartment in dataset.coords['species']:
                    dataset.species_associated_spectra\
                        .loc[{'species': constraint.compartment, model.global_dimension: idx}] \
                        = np.zeros((len(idx)))
                if constraint.compartment == f"{dataset_descriptor.label}_baseline":
                    dataset.baseline.loc[{model.global_dimension: idx}] = np.zeros((len(idx)))

        for relation in model.spectral_relations:
            if relation.compartment in dataset_descriptor.initial_concentration.compartments:
                relation = relation.fill(model, parameter)
                idx = [index.values for index in dataset.spectral if relation.applies(index)]
                all_idx = np.asarray(np.sum([idxs for idxs in global_indices]))
                clp = []
                for i in idx:
                    group_idx = np.abs(all_idx - i).argmin()
                    clp_idx = reduced_clp_labels[group_idx].index(relation.target)
                    clp.append(
                        reduced_clps[group_idx][clp_idx] * relation.parameter
                    )
                sas = xr.DataArray(clp, coords=[(model.global_dimension, idx)])

                dataset.species_associated_spectra\
                    .loc[{'species': relation.compartment, model.global_dimension: idx}] = sas

        if len(dataset.matrix.shape) == 3:
            #  index dependent
            dataset['species_concentration'] = (
                (model.global_dimension, model.matrix_dimension, 'species',),
                dataset.matrix.sel(clp_label=compartments).values)
        else:
            #  index independent
            dataset['species_concentration'] = (
                (model.matrix_dimension, 'species',),
                dataset.matrix.sel(clp_label=compartments).values)

        # get_das
        all_das = []
        all_a_matrix = []
        all_k_matrix = []
        all_das_labels = []
        for megacomplex in dataset_descriptor.megacomplex:

            k_matrix = megacomplex.full_k_matrix()
            if k_matrix is None:
                continue

            compartments = dataset_descriptor.initial_concentration.compartments

            compartments = [c for c in compartments if c in k_matrix.involved_compartments()]

            matrix = k_matrix.full(compartments)
            a_matrix = k_matrix.a_matrix(dataset_descriptor.initial_concentration)
            rates = k_matrix.rates(dataset_descriptor.initial_concentration)
            lifetimes = 1/rates

            das = dataset.species_associated_spectra.sel(species=compartments).values @ a_matrix.T

            component_coords = {
                'rate': ('component', rates),
                'lifetime': ('component', lifetimes)}

            das_coords = component_coords.copy()
            das_coords[model.global_dimension] = dataset.coords[model.global_dimension]
            all_das_labels.append(megacomplex.label)
            print('bla', megacomplex.label, das.shape)
            all_das.append(
                xr.DataArray(
                    das, dims=(model.global_dimension, 'component'),
                    coords=das_coords))
            a_matrix_coords = component_coords.copy()
            a_matrix_coords['species'] = compartments
            all_a_matrix.append(
                xr.DataArray(a_matrix, coords=a_matrix_coords, dims=('component', 'species')))
            all_k_matrix.append(
                xr.DataArray(matrix, coords=[('to_species', compartments),
                                             ('from_species', compartments)]))

        if all_das:
            if len(all_das) == 1:
                dataset['decay_associated_spectra'] = all_das[0]
                dataset['a_matrix'] = all_a_matrix[0]
                dataset['k_matrix'] = all_k_matrix[0]
            else:
                for i, label in enumerate(all_das_labels):
                    dataset[f'decay_associated_spectra_{label}'] = \
                            all_das[i].rename(component=f"component_{label}")
                    dataset[f'a_matrix_{label}'] = all_a_matrix[i] \
                        .rename(component=f"component_{label}")
                    dataset[f'k_matrix_{label}'] = all_k_matrix[i]

        # get_coherent artifact
        irf = dataset_descriptor.irf

        if isinstance(irf, IrfGaussian):

            index = irf.dispersion_center if irf.dispersion_center \
                 else dataset.coords[model.global_dimension].min().values
            dataset['irf'] = (('time'), irf.calculate(index, dataset.coords['time']))

            if irf.dispersion_center:
                for i, dispersion in enumerate(
                        irf.calculate_dispersion(dataset.coords['spectral'].values)):
                    dataset[f'center_dispersion_{i+1}'] = ((model.global_dimension, dispersion))

            if irf.coherent_artifact:
                dataset.coords['coherent_artifact_order'] = \
                        list(range(1, irf.coherent_artifact_order+1))
                dataset['irf_concentration'] = (
                    (model.global_dimension, model.matrix_dimension, 'coherent_artifact_order'),
                    dataset.matrix.sel(clp_label=irf.clp_labels()).values
                )
                dataset['irf_associated_spectra'] = (
                    (model.global_dimension, 'coherent_artifact_order'),
                    dataset.clp.sel(clp_label=irf.clp_labels()).values
                )
