import logging
import numpy as np
from typing import Callable, Dict, Optional, Union
from alibi_detect.utils.frameworks import has_pytorch, has_tensorflow

if has_pytorch:
    from alibi_detect.cd.pytorch.lsdd_online import LSDDDriftOnlineTorch

if has_tensorflow:
    from alibi_detect.cd.tensorflow.lsdd_online import LSDDDriftOnlineTF

logger = logging.getLogger(__name__)


class LSDDDriftOnline:
    def __init__(
            self,
            x_ref: np.ndarray,
            ert: float,
            window_size: int,
            backend: str = 'tensorflow',
            preprocess_x_ref: bool = True,
            preprocess_fn: Optional[Callable] = None,
            sigma: Optional[np.ndarray] = None,
            n_bootstraps: int = 1000,
            n_kernel_centers: Optional[int] = None,
            lambda_rd_max: float = 0.2,
            device: Optional[str] = None,
            input_shape: Optional[tuple] = None,
            data_type: Optional[str] = None
    ) -> None:
        """
        Online least squares density difference (LSDD) data drift detector using preconfigured thresholds.
        Motivated by Bu et al. (2017): https://ieeexplore.ieee.org/abstract/document/7890493
        We have made modifications such that a desired ERT can be accurately targeted however.

        Parameters
        ----------
        x_ref
            Data used as reference distribution.
        ert
            The expected run-time (ERT) in the absence of drift.
        window_size
            The size of the sliding test-window used to compute the test-statistic.
            Smaller windows focus on responding quickly to severe drift, larger windows focus on
            ability to detect slight drift.
        backend
            Backend used for the LSDD implementation and configuration.
        preprocess_x_ref
            Whether to already preprocess and store the reference data.
        preprocess_fn
            Function to preprocess the data before computing the data drift metrics.s
        sigma
            Optionally set the GaussianRBF kernel bandwidth. Can also pass multiple bandwidth values as an array.
            The kernel evaluation is then averaged over those bandwidths.
        n_bootstraps
            The number of bootstrap simulations used to configure the thresholds. The larger this is the
            more accurately the desired ERT will be targeted. Should ideally be at least an order of magnitude
            larger than the ert.
        n_kernel_centers
            Number of reference data points to use kernel centers to use in the estimation of the LSDD.
            Defaults to 2*window_size.
        lambda_rd_max
            The maximum relative difference between two estimates of LSDD that the regularization parameter
            lambda is allowed to cause. Defaults to 0.2 as in the paper.
        device
            Device type used. The default None tries to use the GPU and falls back on CPU if needed.
            Can be specified by passing either 'cuda', 'gpu' or 'cpu'. Only relevant for 'pytorch' backend.
        input_shape
            Shape of input data.
        data_type
            Optionally specify the data type (tabular, image or time-series). Added to metadata.
        """
        super().__init__()

        backend = backend.lower()
        if backend == 'tensorflow' and not has_tensorflow or backend == 'pytorch' and not has_pytorch:
            raise ImportError(f'{backend} not installed. Cannot initialize and run the '
                              f'MMDDrift detector with {backend} backend.')
        elif backend not in ['tensorflow', 'pytorch']:
            raise NotImplementedError(f'{backend} not implemented. Use tensorflow or pytorch instead.')

        kwargs = locals()
        args = [kwargs['x_ref']]
        pop_kwargs = ['self', 'x_ref', 'backend', '__class__']
        [kwargs.pop(k, None) for k in pop_kwargs]

        if backend == 'tensorflow' and has_tensorflow:
            kwargs.pop('device', None)
            self._detector = LSDDDriftOnlineTF(*args, **kwargs)  # type: ignore
        else:
            self._detector = LSDDDriftOnlineTorch(*args, **kwargs)  # type: ignore
        self.meta = self._detector.meta

    @property
    def t(self):
        return self._detector.t

    @property
    def test_stats(self):
        return self._detector.test_stats

    @property
    def thresholds(self):
        thresholds = []
        for s in range(self.t):
            threshold_s = self._detector.thresholds[s] if s < self._detector.window_size else \
                self._detector.thresholds[-1]
            thresholds.append(threshold_s)
        return thresholds

    def reset(self):
        "Resets the detector but does not reconfigure thresholds."
        self._detector.reset()

    def predict(self, x_t: np.ndarray, return_test_stat: bool = True) \
            -> Dict[Dict[str, str], Dict[str, Union[int, float]]]:
        """
        Predict whether the most recent window of data has drifted from the reference data.

        Parameters
        ----------
        x_t
            A single instance to be added to the test-window.
        return_test_stat
            Whether to return the test statistic (LSDD) and threshold.

        Returns
        -------
        Dictionary containing 'meta' and 'data' dictionaries.
        'meta' has the model's metadata.
        'data' contains the drift prediction and optionally the test-statistic and threshold.
        """
        return self._detector.predict(x_t, return_test_stat)