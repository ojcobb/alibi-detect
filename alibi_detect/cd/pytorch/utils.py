from torch import nn
from typing import Callable


def activate_train_mode_for_dropout_layers(model: nn.Module) -> Callable:

    model.eval()
    n_dropout_layers = 0
    for module in model.modules():
        if isinstance(module, nn.Dropout):
            module.train()
            n_dropout_layers += 1
    if n_dropout_layers == 0:
        raise ValueError("No dropout layers identified.")

    return model
