import pytest
from standards import get_security_standard

def test_get_pci_dss_standard():
    standard = get_security_standard("PCI-DSS")
    assert standard is not None
    assert "encryption" in standard.lower()
    assert "cardholder" in standard.lower()
    assert "pci" in standard.lower()

def test_get_soc2_standard():
    standard = get_security_standard("SOC2")
    assert standard is not None
    assert "audit" in standard.lower()
    assert "logging" in standard.lower()

def test_unknown_standard():
    standard = get_security_standard("UNKNOWN")
    assert "not found" in standard.lower()
