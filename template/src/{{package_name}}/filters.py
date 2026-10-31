"""例: 信号処理の純粋関数。入力配列と引数だけで結果が決まり、副作用がない."""

from __future__ import annotations

import numpy as np
from scipy import signal


def lowpass(x: np.ndarray, fs: float, cutoff_hz: float, order: int = 4) -> np.ndarray:
    """ゼロ位相 Butterworth ローパス（最終軸方向）."""
    if not 0 < cutoff_hz < fs / 2:
        raise ValueError(f"cutoff_hz は (0, fs/2) の範囲: {cutoff_hz}")
    sos = signal.butter(order, cutoff_hz, btype="low", fs=fs, output="sos")
    return signal.sosfiltfilt(sos, x, axis=-1)


def snr_db(clean: np.ndarray, estimate: np.ndarray) -> float:
    noise = estimate - clean
    return float(10 * np.log10(np.sum(clean**2) / np.sum(noise**2)))
