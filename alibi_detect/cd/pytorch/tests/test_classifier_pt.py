from itertools import product
import numpy as np
import pytest
import torch
import torch.nn as nn
from alibi_detect.cd.pytorch.classifier import ClassifierDriftTorch

n = 100


class MyModel(nn.Module):
    def __init__(self, n_features: int):
        super().__init__()
        self.dense1 = nn.Linear(n_features, 20)
        self.dense2 = nn.Linear(20, 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = nn.ReLU()(self.dense1(x))
        return self.dense2(x)


p_val = [.05]
n_features = [4]
binarize_preds = [True, False]
n_folds = [None, 2]
train_size = [.5]
update_x_ref = [None, {'last': 1000}, {'reservoir_sampling': 1000}]
tests_clfdrift = list(product(p_val, n_features, binarize_preds, n_folds,
                              train_size, update_x_ref))
n_tests = len(tests_clfdrift)


@pytest.fixture
def clfdrift_params(request):
    return tests_clfdrift[request.param]


@pytest.mark.parametrize('clfdrift_params', list(range(n_tests)), indirect=True)
def test_clfdrift(clfdrift_params):
    p_val, n_features, binarize_preds, n_folds, train_size, update_x_ref = clfdrift_params

    np.random.seed(0)
    torch.manual_seed(0)

    model = MyModel(n_features)
    x_ref = np.random.randn(*(n, n_features)).astype(np.float32)
    x_test0 = x_ref.copy()
    x_test1 = np.ones_like(x_ref)

    cd = ClassifierDriftTorch(
        x_ref=x_ref,
        model=model,
        p_val=p_val,
        update_x_ref=update_x_ref,
        train_size=train_size,
        n_folds=n_folds,
        binarize_preds=binarize_preds,
        batch_size=1
    )

    preds_0 = cd.predict(x_test0)
    assert cd.n == x_test0.shape[0] + x_ref.shape[0]
    assert preds_0['data']['is_drift'] == 0
    assert preds_0['data']['distance'] >= 0

    preds_1 = cd.predict(x_test1)
    assert cd.n == x_test1.shape[0] + x_test0.shape[0] + x_ref.shape[0]
    assert preds_1['data']['is_drift'] == 1
    assert preds_1['data']['distance'] >= 0

    assert preds_0['data']['distance'] < preds_1['data']['distance']
    assert cd.meta['params']['binarize_preds '] == binarize_preds
