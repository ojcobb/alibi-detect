import tensorflow as tf
import numpy as np
from . import distance
from typing import Optional, Union
from scipy.special import logit

class GaussianRBF(tf.keras.Model):
    def __init__(self, sigma: Optional[tf.Tensor] = None, trainable: bool = False) -> None:
        """
        Gaussian RBF kernel: k(x,y) = exp(-(1/(2*sigma^2)||x-y||^2). A forward pass takes
        a batch of instances x [Nx, features] and y [Ny, features] and returns the kernel
        matrix [Nx, Ny].

        Parameters
        ----------
        sigma
            Bandwidth used for the kernel. Needn't be specified if being inferred or trained.
            Can pass multiple values to eval kernel with and then average.
        trainable
            Whether or not to track gradients w.r.t. sigma to allow it to be trained.
        """
        super().__init__()
        if sigma is None:
            self.log_sigma = tf.Variable(np.empty(1), dtype=tf.float32, trainable=trainable)
            self.init_required = True
        else:
            sigma = sigma.reshape(-1)  # [Ns,]
            self.log_sigma = tf.Variable(sigma.log(), trainable=trainable)
            self.init_required = False
        self.trainable = trainable

    @property
    def sigma(self) -> tf.Tensor:
        return tf.math.exp(self.log_sigma)

    def call(self, x: tf.Tensor, y: tf.Tensor, infer_sigma: bool = False) -> tf.Tensor:

        x, y = tf.reshape(x, (x.shape[0], -1)), tf.reshape(y, (y.shape[0], -1)) # flatten
        dist = distance.squared_pairwise_distance(x, y)  # [Nx, Ny]

        if infer_sigma or self.init_required:
            if self.trainable and infer_sigma:
                raise ValueError("Gradients cannot be computed w.r.t. an inferred sigma value")
            n = min(x.shape[0], y.shape[0])
            n = n if tf.reduce_all(x[:n] == y[:n]) and x.shape == y.shape else 0
            n_median = n + (tf.math.reduce_prod(dist.shape) - n) // 2 - 1
            sigma = tf.expand_dims((.5 * tf.sort(tf.reshape(dist, (-1,)))[n_median]) ** .5, axis=0)
            self.log_sigma.assign(tf.math.log(sigma))
            if self.trainable:
                self.init_required = False  # if not trainable will keep inferring sigma anew

        gamma = 1. / (2. * self.sigma ** 2)   # [Ns,]
        # TODO: do matrix multiplication after all?
        kernel_mat = tf.exp(- tf.concat([(g * dist)[None, :, :] for g in gamma], axis=0))  # [Ns, Nx, Ny]
        return tf.reduce_mean(kernel_mat, axis=0)  # [Nx, Ny]


class DeepKernel(tf.keras.Model):
    """"
    Computes simmilarities as k(x,y) = (1-eps)*k_a(proj(x), proj(y)) + eps*k_b(x,y)
    """
    def __init__(
        self,
        proj: tf.keras.Model,
        kernel_a: tf.keras.Model = GaussianRBF(trainable=True),
        kernel_b: tf.keras.Model = GaussianRBF(trainable=True),
        eps: Union[float, str] = 'trainable'
    ) -> None:
        super().__init__()

        self.kernel_a = kernel_a
        self.kernel_b = kernel_b
        self.proj = proj
        if isinstance(eps, float):
            if not 0 < eps < 1:
                raise ValueError("eps should be in (0,1)")
            eps = tf.constant(eps)
            self.logit_eps = tf.Variable(tf.constant(logit(eps)), trainable=False)
        elif eps == 'trainable':
            self.logit_eps = tf.Variable(tf.constant(0.))
        else:
            raise NotImplementedError("eps should be 'trainable' or a float in (0,1)")

    @property
    def eps(self) -> tf.Tensor:
        return tf.math.sigmoid(self.logit_eps)

    def call(self, x: tf.Tensor, y: tf.Tensor):
        return (
            (1-self.eps)*self.kernel_a(self.proj(x), self.proj(y)) +
            self.eps*self.kernel_b(x, y)
        )
