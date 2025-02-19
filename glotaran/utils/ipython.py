"""Glotaran module with utilities for ``ipython`` integration (e.g. ``notebooks``)."""
from __future__ import annotations

from collections import UserString

from glotaran.plugin_system.io_plugin_utils import infer_file_format
from glotaran.typing.types import StrOrPath


class MarkdownStr(UserString):
    """String wrapper class for rich display integration of markdown in ipython."""

    def __init__(self, wrapped_str: str, *, syntax: str | None = None):
        """Initialize string class that is automatically displayed as markdown by ``ipython``.

        Parameters
        ----------
        wrapped_str: str
            String to be wrapped.
        syntax: str
            Syntax highlighting which should be applied, by default None

        Note
        ----
        Possible syntax highlighting values can e.g. be found here:
        https://support.codebasehq.com/articles/tips-tricks/syntax-highlighting-in-markdown


        .. # noqa: DAR101
        """
        # This needs to be called data since ipython is looking for this attr
        self.data = str(wrapped_str)
        self.syntax = syntax

    def _repr_markdown_(self) -> str:
        """Render markdown automatically when in a ``ipython`` context.

        See:
        https://ipython.readthedocs.io/en/latest/config/integrating.html?highlight=_repr_markdown_#rich-display

        Returns
        -------
        str:
            Markdown string wrapped in a code block with syntax
            highlighting if syntax is not None.
        """
        if self.syntax is not None:
            return f"```{self.syntax}\n{self.data}\n```"
        else:
            return self.data

    def __str__(self) -> str:
        """Representation used by print and str."""
        return self._repr_markdown_()

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        if isinstance(other, (str, MarkdownStr)):
            return str(self) == str(other)
        else:
            return NotImplemented


def display_file(path: StrOrPath, *, syntax: str | None = None) -> MarkdownStr:
    """Display a file with syntax highlighting ``syntax``.

    Parameters
    ----------
    path : StrOrPath
        Paths to the file
    syntax: str | None
        Syntax used for syntax highlighting. Defaults to None which means that the syntax is
        inferred based on the file extension. Pass the value ``""`` to deactivate syntax
        highlighting.

    Returns
    -------
    MarkdownStr
        File content with syntax highlighting to render in ipython.
    """
    if syntax is None:
        syntax = infer_file_format(path)
    with open(path, encoding="utf8") as file:
        return MarkdownStr(file.read(), syntax=syntax)
