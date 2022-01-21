from __future__ import annotations

import pytest
from IPython.core.formatters import format_display_data

from glotaran.analysis.optimize import optimize
from glotaran.project.result import Result
from glotaran.testing.simulated_data.sequential_spectral_decay import SCHEME


@pytest.fixture(scope="session")
def dummy_result():
    """Dummy result for testing."""
    print(SCHEME.data["dataset_1"])
    yield optimize(SCHEME, raise_exception=True)


def test_result_ipython_rendering(dummy_result: Result):
    """Autorendering in ipython"""

    rendered_obj = format_display_data(dummy_result)[0]

    assert "text/markdown" in rendered_obj
    assert rendered_obj["text/markdown"].startswith("| Optimization Result")

    rendered_markdown_return = format_display_data(dummy_result.markdown())[0]

    assert "text/markdown" in rendered_markdown_return
    assert rendered_markdown_return["text/markdown"].startswith("| Optimization Result")
