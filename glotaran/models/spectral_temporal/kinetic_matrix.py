""" Glotaran Kinetic Matrix """

from typing import List, Tuple
import numpy as np
import scipy.linalg
import lmfit

from glotaran.fitmodel import Matrix
from glotaran.model import CompartmentConstraintType, Model

from .c_matrix_cython.c_matrix_cython import CMatrixCython

_BACKEND = CMatrixCython()


class KineticMatrix(Matrix):
    """Implementation of fitmodel.Matrix for a kinetic model."""
    def __init__(self, x: float, dataset: str, model: Model):
        """

        Parameters
        ----------
        x : float
            Point on the estimated axis the matrix calculated for

        dataset : str
            Dataset label of the dataset the matrix is calculated for

        model : glotaran.Model
            The model the matrix is calculated for


        """

        super(KineticMatrix, self).__init__(x, dataset, model)

        self._irf = None
        self._collect_irf(model)
        self._disp_center = dataset.dispersion_center

        self._k_matrices = []
        self._megacomplex_scaling = []
        self._collect_k_matrices(model)
        self._set_compartment_order(model)

        self._initial_concentrations = None
        self._collect_initial_concentration(model)

    @property
    def compartment_order(self) -> List[str]:
        """A list with compartment labels. The index of label indicates the
        index of the compartment in the matrix."""
        return self._compartment_order

    @property
    def shape(self) -> Tuple[int, int]:
        """The matrix dimensions as tuple(M, N)."""
        return (self.time.shape[0], len(self._compartment_order))

    def _set_compartment_order(self, model):
        """Sets the compartment order to map compartment labels to indices in
        the matrix"""
        compartment_order = [c for mat in self._k_matrices
                             for c in mat.compartment_map]

        compartment_order = list(set(compartment_order))
        self._compartment_order = [c for c in model.compartments if c in
                                   compartment_order]

    def _collect_irf(self, model):
        if self.dataset.irf is None:
            return
        self._irf = model.irfs[self.dataset.irf]

    def _collect_k_matrices(self, model):
        for cmplx in [model.megacomplexes[mc] for mc in self.dataset.megacomplexes]:
            model_k_matrix = None
            for k_matrix_label in cmplx.k_matrices:
                mat = model.k_matrices[k_matrix_label]

                # If multiple k matrices are present, we combine them
                if model_k_matrix is None:
                    model_k_matrix = mat
                else:
                    model_k_matrix = model_k_matrix.combine(mat)
            scaling = self.dataset.megacomplex_scaling[cmplx.label] \
                if cmplx.label in self.dataset.megacomplex_scaling else None
            self._megacomplex_scaling.append(scaling)
            self._k_matrices.append(model_k_matrix)

    def _collect_initial_concentration(self, model):
        if self.dataset.initial_concentration is None:
            return
        initial_concentrations = \
            model.initial_concentrations[self.dataset.initial_concentration]

        # The initial concentration vector has an element for each compartment
        # declared in the model. The current C Matrix must not necessary invole
        # all compartments, as well as the order of compartments can be
        # different. Thus we shrink and reorder the concentration.

        all_cmps = model.compartments

        self._initial_concentrations = \
            [initial_concentrations.parameter[all_cmps.index(c)]
             for c in self.compartment_order]

    def calculate(self,
                  matrix: np.array,
                  compartment_order: List[str],
                  parameter: lmfit.Parameters):
        """ Calculates the matrix.

        Parameters
        ----------
        matrix : np.array
            The preallocated matrix.

        compartment_order : list(str)
            A list of compartment labels to map compartments to indices in the
            matrix.

        parameter : lmfit.Parameters
            A dictory of parameters.


        Returns
        -------

        """

        for k_matrix, scale in self._k_matrices_and_scalings():

            scale = parameter.get(scale) if scale is not None else 1.0
            scale *= self._dataset_scaling(parameter)

            self._calculate_for_k_matrix(matrix, compartment_order, k_matrix,
                                         parameter, scale)

    def _k_matrices_and_scalings(self):
        """ Iterator of k matrices and scalings"""
        for i in range(len(self._k_matrices)):
            yield self._k_matrices[i], self._megacomplex_scaling[i]

    def _calculate_for_k_matrix(self,
                                matrix: np.array,
                                compartment_order: List[str],
                                k_matrix: str,
                                parameter: lmfit.Parameters,
                                scale: str):
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-arguments

        # calculate k_matrix eigenvectos
        eigenvalues, eigenvectors = self._calculate_k_matrix_eigen(k_matrix,
                                                                   parameter)
        rates = -eigenvalues

        # we need this since the full c matrix can have more compartments then
        # the k matrix
        compartment_idxs = [compartment_order.index(c) for c in
                            k_matrix.compartment_map]

        # get constraint compartment indeces
        constraint_compartments = [c.compartment for c in
                                   self.dataset.compartment_constraints if
                                   c.applies(self.index) and c.type() is not
                                   CompartmentConstraintType.equal_area]
        constraint_idx = [k_matrix.compartment_map.index(c) for c in
                          constraint_compartments]

        # TODO: do not delete column prior to c-matrix evaluation
        rates = np.delete(rates, constraint_idx)
        compartment_idxs = np.delete(compartment_idxs, constraint_idx)

        # get the time axis
        time = self.dataset.dataset.get_axis("time")

        # calculate the c_matrix
        if self._irf is None:
            _BACKEND.c_matrix(matrix, compartment_idxs, rates, time,
                              scale)
        else:
            centers, widths, irf_scale, backsweep, backsweep_period = \
                    self._calculate_irf_parameter(parameter)
            _BACKEND.c_matrix_gaussian_irf(matrix,
                                           compartment_idxs,
                                           rates,
                                           time,
                                           centers, widths,
                                           scale * irf_scale,
                                           backsweep,
                                           backsweep_period,
                                           )
        # Apply equal equal constraints
        for constrain in self.dataset.compartment_constraints:
            if constrain.type() is CompartmentConstraintType.equal and \
              constrain.applies(self.index):
                idx = compartment_order.index(constrain.compartment)
                for target, param in constrain.targets_and_parameter:
                    t_idx = compartment_order.index(target)
                    param = parameter.get(param)
                    matrix[:, idx] += param * matrix[:, t_idx]

        if self._initial_concentrations is not None:
            self._apply_initial_concentration_vector(matrix,
                                                     eigenvectors,
                                                     parameter,
                                                     compartment_order)

    def _calculate_k_matrix_eigen(self, k_matrix, parameter):
        """

        Parameters
        ----------
        k_matrix :

        parameter :


        Returns
        -------

        """
        # pylint: disable=no-self-use
        k_matrix = k_matrix.full(parameter)
        # get the eigenvectors and values
        eigenvalues, eigenvectors = np.linalg.eig(k_matrix)
        return (eigenvalues.real, eigenvectors.real)

    def _calculate_irf_parameter(self, parameter):
        """

        Parameters
        ----------
        parameter :


        Returns
        -------

        """

        centers = np.asarray([parameter.get(i) for i in self._irf.center])
        widths = np.asarray([parameter.get(i) for i in self._irf.width])

        center_dispersion = \
            np.asarray([parameter.get(i) for i in self._irf.center_dispersion]) \
            if len(self._irf.center_dispersion) is not 0 else []

        width_dispersion = \
            np.asarray([parameter.get(i) for i in self._irf.width_dispersion]) \
            if len(self._irf.width_dispersion) is not 0 else []

        dist = (self.index - self._disp_center)/100
        if len(center_dispersion) is not 0:
            for i, disp in enumerate(center_dispersion):
                centers = centers + disp * np.power(dist, i+1)

        if len(width_dispersion) is not 0:
            for i, disp in enumerate(width_dispersion):
                widths = widths + disp * np.power(dist, i+1)

        if len(self._irf.scale) is 0:
            scale = np.ones(centers.shape)
        else:
            scale = np.asarray([parameter.get(i) for i in self._irf.scale])

        backsweep = 1 if self._irf.backsweep else 0

        backsweep_period = parameter.get(self._irf.backsweep_period) \
            if self._irf.backsweep else 0

        return centers, widths, scale, backsweep, backsweep_period

    def _apply_initial_concentration_vector(self, c_matrix, eigenvectors,
                                            parameter, compartment_order):
        """

        Parameters
        ----------
        c_matrix :

        eigenvectors :

        parameter :

        compartment_order :


        Returns
        -------

        """

        initial_concentrations = [parameter.get(i) for i in self._initial_concentrations]

        initial_concentrations = \
            [initial_concentrations[compartment_order.index(c)] for c in
             self.compartment_order]

        gamma = np.matmul(scipy.linalg.inv(eigenvectors),
                          initial_concentrations)

        concentration_matrix = np.empty(eigenvectors.shape,
                                        dtype=np.float64)

        for i in range(eigenvectors.shape[0]):
            concentration_matrix[i, :] = eigenvectors[:, i] * gamma[i]

        np.dot(np.copy(c_matrix), concentration_matrix, out=c_matrix)

    @property
    def time(self):
        """The time axis of the matrix """
        return self.dataset.dataset.get_axis("time")

    def _dataset_scaling(self, parameter: lmfit.Parameters):
        """Gets the dataset scaling value from the parameters.

        Parameters
        ----------
        parameter :


        Returns
        -------

        """
        return parameter.get(self.dataset.scaling) if self.dataset.scaling is not None else 1.0
