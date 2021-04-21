import numpy as np
import pytest
from functools import partial
from itertools import product
import scipy
import tensorflow as tf
from tensorflow.keras.layers import Dense, Input, Softmax, Dropout
import torch
import torch.nn as nn
from alibi_detect.cd import ClassifierUncertaintyDrift, RegressorUncertaintyDrift

n = 500


def tf_model(n_features, n_labels, softmax=False, dropout=False):
    x_in = Input(shape=(n_features,))
    x = Dense(20, activation=tf.nn.relu)(x_in)
    if dropout:
        x = Dropout(0.5)(x)
    x = Dense(n_labels)(x)
    if softmax:
        x = Softmax()(x)
    return tf.keras.models.Model(inputs=x_in, outputs=x)


class PtModel(nn.Module):
    def __init__(self, n_features, n_labels, softmax=False, dropout=False):
        super().__init__()
        self.dense1 = nn.Linear(n_features, 20)
        self.dense2 = nn.Linear(20, n_labels)
        self.dropout = nn.Dropout(0.5) if dropout else lambda x: x
        self.softmax = nn.Softmax() if softmax else lambda x: x

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = nn.ReLU()(self.dense1(x))
        x = self.dropout(x)
        x = self.dense2(x)
        x = self.softmax(x)
        return x


def dumb_model(x, n_labels, softmax=False):
    x = np.stack([np.mean(x*(i+1), axis=-1) for i in range(n_labels)], axis=-1)
    if softmax:
        x = scipy.special.softmax(x, axis=-1)
    return x


# def other_model(preds_type):
#     if preds_type == 'probs':
#         return partial(dumb_model, preds_type='probs')
#     elif preds_type == 'logits':
#         return partial(dumb_model, preds_type='logits')


def gen_model(n_features, n_labels, backend, softmax=False, dropout=False):
    if backend == 'tensorflow':
        return tf_model(n_features, n_labels, softmax, dropout)
    elif backend == 'pytorch':
        return PtModel(n_features, n_labels, softmax, dropout)
    elif backend is None:
        return partial(dumb_model, n_labels=n_labels, softmax=softmax)


p_val = [.05]
backend = ['tensorflow', 'pytorch', None]
n_features = [16]
n_labels = [3]
preds_type = ['probs', 'logits']
uncertainty_type = ['entropy', 'margin']
update_x_ref = [None, {'last': 1000}, {'reservoir_sampling': 1000}]
tests_clfuncdrift = list(product(p_val, backend, n_features, n_labels, preds_type, uncertainty_type, update_x_ref))
n_tests = len(tests_clfuncdrift)


@pytest.fixture
def clfuncdrift_params(request):
    return tests_clfuncdrift[request.param]


@pytest.mark.parametrize('clfuncdrift_params', list(range(n_tests)), indirect=True)
def test_clfuncdrift(clfuncdrift_params):
    p_val, backend, n_features, n_labels, preds_type, uncertainty_type, update_x_ref = clfuncdrift_params

    np.random.seed(0)
    tf.random.set_seed(0)

    model = gen_model(n_features, n_labels, backend, preds_type == 'probs')
    x_ref = np.random.randn(*(n, n_features)).astype(np.float32)
    x_test0 = x_ref.copy()
    x_test1 = np.ones_like(x_ref)

    cd = ClassifierUncertaintyDrift(
        x_ref=x_ref,
        model=model,
        p_val=p_val,
        backend=backend,
        update_x_ref=update_x_ref,
        preds_type=preds_type,
        uncertainty_type=uncertainty_type,
        margin_width=0.1,
        batch_size=10
    )

    preds_0 = cd.predict(x_test0)
    assert cd._detector.n == x_test0.shape[0] + x_ref.shape[0]
    assert preds_0['data']['is_drift'] == 0
    assert preds_0['data']['distance'] >= 0

    preds_1 = cd.predict(x_test1)
    assert cd._detector.n == x_test1.shape[0] + x_test0.shape[0] + x_ref.shape[0]
    if not preds_1['data']['is_drift'] == 1:
        breakpoint()
    assert preds_1['data']['is_drift'] == 1
    assert preds_1['data']['distance'] >= 0

    assert preds_0['data']['distance'] < preds_1['data']['distance']
    assert cd.meta['params']['preds_type'] == preds_type
    assert cd.meta['params']['uncertainty_type'] == uncertainty_type


p_val = [.05]
backend = ['tensorflow', 'pytorch']
n_features = [16]
uncertainty_type = ['mc_dropout', 'ensemble']
update_x_ref = [None, {'last': 1000}, {'reservoir_sampling': 1000}]
tests_reguncdrift = list(product(p_val, backend, n_features, uncertainty_type, update_x_ref))
n_tests = len(tests_reguncdrift)


@pytest.fixture
def reguncdrift_params(request):
    return tests_reguncdrift[request.param]


@pytest.mark.parametrize('reguncdrift_params', list(range(n_tests)), indirect=True)
def test_reguncdrift(reguncdrift_params):
    p_val, backend, n_features, uncertainty_type, update_x_ref = reguncdrift_params

    np.random.seed(0)
    tf.random.set_seed(0)

    if uncertainty_type == 'mc_dropout':
        n_labels = 1
        dropout = True
    elif uncertainty_type == 'ensemble':
        n_labels = 5
        dropout = False

    model = gen_model(n_features, n_labels, backend, dropout=dropout)
    x_ref = np.random.randn(*(n, n_features)).astype(np.float32)
    x_test0 = x_ref.copy()
    x_test1 = np.ones_like(x_ref)

    cd = RegressorUncertaintyDrift(
        x_ref=x_ref,
        model=model,
        p_val=p_val,
        backend=backend,
        update_x_ref=update_x_ref,
        uncertainty_type=uncertainty_type,
        n_evals=5,
        batch_size=10
    )

    preds_0 = cd.predict(x_test0)
    assert cd._detector.n == x_test0.shape[0] + x_ref.shape[0]
    assert preds_0['data']['is_drift'] == 0
    assert preds_0['data']['distance'] >= 0

    preds_1 = cd.predict(x_test1)
    assert cd._detector.n == x_test1.shape[0] + x_test0.shape[0] + x_ref.shape[0]
    assert preds_1['data']['is_drift'] == 1
    assert preds_1['data']['distance'] >= 0

    assert preds_0['data']['distance'] < preds_1['data']['distance']
    assert cd.meta['params']['uncertainty_type'] == uncertainty_type
