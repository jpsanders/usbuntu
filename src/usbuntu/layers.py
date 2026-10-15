"""Selection of the squashfs layers that make up a full Ubuntu system.

Ubuntu desktop ISOs since 24.04 are built as a stack of squashfs overlay
layers instead of one filesystem image:

* a base layer, such as ``minimal.squashfs`` (26.04) or ``ubuntu-desktop-minimal.squashfs`` (24.04)
* a full-desktop layer on top, such as ``minimal.standard.squashfs``
* tiny per-language layers, such as ``minimal.standard.en.squashfs``
* special layers that must never land on an installed stick:

  * ``*.live.*`` exists only for the live session
  * ``*.enhanced-secureboot.*`` whiteouts out the deb kernel in ``/boot``
    in favour of Ubuntu's snapd-managed boot flow, which conflicts with a
    classic GRUB install

This module walks the layer tree and returns the chain for the requested
flavour and language, bottom layer first.
"""

from collections.abc import Mapping

EXCLUDED_SEGMENTS = frozenset({"live", "enhanced-secureboot"})


class LayerError(Exception):
    """Raised when a usable layer chain cannot be built."""


def _segments(layer: str) -> list[str]:
    """
    Split a layer name into its dot separated segments.

    :param layer: Layer name without the ``.squashfs`` suffix
    :returns: The segments, such as ``['minimal', 'standard', 'en']``
    """
    return layer.split(".")


def is_language(segment: str) -> bool:
    """
    Say whether a name segment is a language selector rather than a structural one.

    :param segment: A single dot separated segment
    :returns: True for language codes and the ``no-languages`` marker
    """
    if segment == "no-languages":
        return True
    return len(segment) <= 3 and segment.isalpha() and segment.islower()


def discover_base(layers: Mapping[str, int]) -> str:
    """
    Find the base layer of an ISO.

    The base has the fewest name segments; where an ISO ships more than one
    candidate, the largest file wins.

    :param layers: Layer name to file size in bytes
    :returns: The base layer name
    :raises LayerError: When there is no plausible base layer
    """
    if not layers:
        raise LayerError("no squashfs layers found in the ISO")
    fewest = min(len(_segments(name)) for name in layers)
    candidates = [name for name in layers if len(_segments(name)) == fewest]
    base = max(candidates, key=lambda name: layers[name])
    if layers[base] < 64 * 1024 * 1024:
        raise LayerError(f"base layer {base!r} is only {layers[base]} bytes, this does not look like a root filesystem")
    return base


def _structural_child(layer: str, layers: Mapping[str, int]) -> str | None:
    """
    Find the structural, non-language child of a layer, such as ``standard``.

    :param layer: The parent layer name
    :param layers: Layer name to file size in bytes
    :returns: The largest structural child, or None when there is none
    """
    prefix = f"{layer}."
    children = [
        name
        for name in layers
        if name.startswith(prefix)
        and len(_segments(name)) == len(_segments(layer)) + 1
        and not is_language(_segments(name)[-1])
        and _segments(name)[-1] not in EXCLUDED_SEGMENTS
    ]
    if not children:
        return None
    return max(children, key=lambda name: layers[name])


def _language_child(layer: str, layers: Mapping[str, int], language: str) -> str | None:
    """
    Find the language layer for a parent, falling back to ``no-languages``.

    :param layer: The parent layer name
    :param layers: Layer name to file size in bytes
    :param language: The requested language code, such as ``en``
    :returns: The language layer name, or None when the parent has none
    """
    if f"{layer}.{language}" in layers:
        return f"{layer}.{language}"
    if f"{layer}.no-languages" in layers:
        return f"{layer}.no-languages"
    return None


def build_chain(layers: Mapping[str, int], flavor: str, language: str) -> list[str]:
    """
    Build the bottom-up layer chain for an install.

    For a 26.04 ISO with ``flavor='full'`` and ``language='en'`` the chain is
    ``['minimal', 'minimal.en', 'minimal.standard', 'minimal.standard.en']``.
    Older ISOs with a single ``filesystem.squashfs`` return that one name.

    :param layers: Layer name to file size in bytes, from the ISO's casper directory
    :param flavor: ``full`` for the complete desktop, ``minimal`` for the reduced one
    :param language: The requested language code, such as ``en``
    :returns: The layer names, bottom layer first
    :raises LayerError: When the flavor or a needed layer cannot be resolved
    """
    if flavor not in ("full", "minimal"):
        raise LayerError(f"unknown flavor {flavor!r}")
    base = discover_base(layers)
    chain: list[str] = [base]
    if flavor == "full":
        tier = _structural_child(base, layers)
        if tier is None:
            raise LayerError(
                f"the ISO has no full desktop layer on top of {base!r}; try --flavor minimal"
            )
        chain.append(tier)
    for parent in list(chain):
        language_layer = _language_child(parent, layers, language)
        if language_layer is not None:
            chain.insert(chain.index(parent) + 1, language_layer)
    return chain
