"""Tests for the layer chain selection."""

import pytest

from usbuntu.layers import LayerError, build_chain, discover_base, is_language

LAYERS_2604 = {
    "minimal": 3_436_847_104,
    "minimal.de": 17_000_000,
    "minimal.en": 17_000_000,
    "minimal.es": 17_000_000,
    "minimal.pt": 17_000_000,
    "minimal.no-languages": 17_000_000,
    "minimal.enhanced-secureboot": 17_000_000,
    "minimal.enhanced-secureboot.en": 2_100_000,
    "minimal.enhanced-secureboot.no-languages": 2_100_000,
    "minimal.standard": 563_000_000,
    "minimal.standard.en": 2_900_000,
    "minimal.standard.no-languages": 2_900_000,
    "minimal.standard.enhanced-secureboot": 2_400_000,
    "minimal.standard.enhanced-secureboot.en": 2_900_000,
    "minimal.standard.live": 757_000_000,
}

LAYERS_2404 = {
    "ubuntu-desktop-minimal": 3_000_000_000,
    "ubuntu-desktop-minimal.en": 40_000_000,
    "ubuntu-desktop-minimal.ubuntu-desktop": 1_100_000_000,
    "ubuntu-desktop-minimal.ubuntu-desktop.en": 60_000_000,
}

LAYERS_LEGACY = {"filesystem": 2_000_000_000}


class TestIsLanguage:
    def test_language_codes(self) -> None:
        assert is_language("en")
        assert is_language("pt")
        assert is_language("zh")
        assert is_language("no-languages")

    def test_structural_segments(self) -> None:
        assert not is_language("minimal")
        assert not is_language("standard")
        assert not is_language("ubuntu-desktop")
        assert not is_language("live")


class TestDiscoverBase:
    def test_finds_largest_layer_with_fewest_segments(self) -> None:
        assert discover_base(LAYERS_2604) == "minimal"

    def test_legacy_single_layer(self) -> None:
        assert discover_base(LAYERS_LEGACY) == "filesystem"

    def test_empty_iso_raises(self) -> None:
        with pytest.raises(LayerError):
            discover_base({})

    def test_tiny_base_raises(self) -> None:
        with pytest.raises(LayerError):
            discover_base({"small": 1_000})


class TestBuildChain:
    def test_full_2604_chain(self) -> None:
        chain = build_chain(LAYERS_2604, "full", "en")
        assert chain == ["minimal", "minimal.en", "minimal.standard", "minimal.standard.en"]

    def test_minimal_2604_chain(self) -> None:
        chain = build_chain(LAYERS_2604, "minimal", "en")
        assert chain == ["minimal", "minimal.en"]

    def test_language_falls_back_to_no_languages(self) -> None:
        chain = build_chain(LAYERS_2604, "full", "fr")
        assert chain == [
            "minimal",
            "minimal.no-languages",
            "minimal.standard",
            "minimal.standard.no-languages",
        ]

    def test_2404_naming_style(self) -> None:
        chain = build_chain(LAYERS_2404, "full", "en")
        assert chain == [
            "ubuntu-desktop-minimal",
            "ubuntu-desktop-minimal.en",
            "ubuntu-desktop-minimal.ubuntu-desktop",
            "ubuntu-desktop-minimal.ubuntu-desktop.en",
        ]

    def test_legacy_iso_stays_a_single_layer(self) -> None:
        assert build_chain(LAYERS_LEGACY, "minimal", "en") == ["filesystem"]

    def test_live_layer_never_lands_in_a_chain(self) -> None:
        chain = build_chain(LAYERS_2604, "full", "en")
        assert "minimal.standard.live" not in chain

    def test_secureboot_layer_never_lands_in_a_chain(self) -> None:
        chain = build_chain(LAYERS_2604, "full", "en")
        assert "minimal.standard.enhanced-secureboot" not in chain
        assert "minimal.standard.enhanced-secureboot.en" not in chain
        assert "minimal.enhanced-secureboot" not in chain

    def test_full_flavor_on_legacy_iso_raises_with_hint(self) -> None:
        with pytest.raises(LayerError, match="minimal"):
            build_chain(LAYERS_LEGACY, "full", "en")

    def test_unknown_flavor_raises(self) -> None:
        with pytest.raises(LayerError):
            build_chain(LAYERS_2604, "everything", "en")
