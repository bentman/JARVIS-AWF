import subprocess

import pytest

from awf.hardware.gpu_sampler import (
    GPU_UTILIZATION_CEILING,
    GpuSamplerUnavailable,
    exceeds_ceiling,
    sample_gpu_utilization,
)


def test_exceeds_ceiling():
    assert exceeds_ceiling(GPU_UTILIZATION_CEILING + 0.01) is True
    assert exceeds_ceiling(GPU_UTILIZATION_CEILING) is False
    assert exceeds_ceiling(0.0) is False


@pytest.mark.live
def test_sample_gpu_utilization_returns_fraction_in_range_or_raises(gpu_available):
    if not gpu_available:
        pytest.skip("no nvidia-smi/GPU on this host")
    utilization = sample_gpu_utilization()
    assert 0.0 <= utilization <= 1.0


def test_unavailable_when_nvidia_smi_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi not found")

    monkeypatch.setattr("awf.hardware.gpu_sampler.subprocess.run", fake_run)

    with pytest.raises(GpuSamplerUnavailable):
        sample_gpu_utilization()


def test_unavailable_on_nonzero_exit(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="no devices")

    monkeypatch.setattr("awf.hardware.gpu_sampler.subprocess.run", fake_run)

    with pytest.raises(GpuSamplerUnavailable):
        sample_gpu_utilization()
