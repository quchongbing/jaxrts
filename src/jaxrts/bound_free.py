"""
This submodule is dedicated to calculate the contribution of tightly bound electrons to the dynamic structure factor.
"""

from .units import ureg, Quantity
from typing import List

import jax
from jax import jit
import jax.numpy as jnp
import jpu.numpy as jnpu
import numpy as onp

import logging

logger = logging.getLogger(__name__)

from .form_factors import pauling_atomic_ff
from .plasma_physics import thomson_momentum_transfer
import jpu


def _xi(n: int, Zeff: Quantity, omega: Quantity, k: Quantity):
    omega_c = (ureg.hbar * k**2) / (2 * ureg.m_e)
    q = (omega - omega_c) / (ureg.c * k)
    return (n * q) / (Zeff * ureg.alpha)


def _J10_BM(omega: Quantity, k: Quantity, Zeff: Quantity) -> Quantity:
    xi = _xi(1, Zeff, omega, k)
    return 8 / (3 * jnp.pi * Zeff * ureg.alpha * (1 + xi**2) ** 3)


def _J20_BM(omega: Quantity, k: Quantity, Zeff: Quantity) -> Quantity:
    xi = _xi(2, Zeff, omega, k)
    return (64 / (jnp.pi * Zeff * ureg.alpha)) * (
        (1 / (3 * (1 + xi**2) ** 3))
        - (1 / (1 + xi**2) ** 4)
        + (4 / (5 * (1 + xi**2) ** 5))
    )


def _J21_BM(omega: Quantity, k: Quantity, Zeff: Quantity) -> Quantity:
    xi = _xi(2, Zeff, omega, k)
    return (64 / (15 * jnp.pi * Zeff * ureg.alpha)) * (
        (1 + 5 * xi**2) / (1 + xi**2) ** 5
    )


def _J10_HR(omega: Quantity, k: Quantity, Zeff: Quantity) -> Quantity:
    """
    :cite:`Gregori.2004`, eqn (16)
    """
    xi = _xi(1, Zeff, omega, k)
    J10BM = _J10_BM(omega, k, Zeff)
    return J10BM * (Zeff * ureg.alpha / (k * ureg.a_0)) * (3 / 2 * xi - 2 * jnpu.arctan(xi))

def _J20_HR(omega: Quantity, k: Quantity, Zeff: Quantity) -> Quantity:
    """
    :cite:`Gregori.2004`, eqn (17)
    """
    xi = _xi(2, Zeff, omega, k)
    J20BM = _J20_BM(omega, k, Zeff)
    return (
        J20BM
        * (Zeff * ureg.alpha / (k * ureg.a_0))
        * (
            5
            * xi
            * (1 + 3 * xi**4)
            / (1 - 2.5 * xi**2 + 2.5 * xi**4)
            / 8
            - 2 * jnpu.arctan(xi)
        )
    )

def _J21_HR(omega: Quantity, k: Quantity, Zeff: Quantity) -> Quantity:
    """
    :cite:`Gregori.2004`, eqn (18)
    """
    xi = _xi(2, Zeff, omega, k)
    J21BM = _J21_BM(omega, k, Zeff)
    return (
        J21BM
        * (Zeff * ureg.alpha / (k * ureg.a_0))
        * (
            (1 / 3) * ((10 + 15 * xi**2) / (1 + 5 * xi**2)) * xi
            - jnpu.arctan(xi)
        )
    )

def bm_bound_wavefunction(
    n: int,
    l: int,  # noqa E741
    omega: Quantity,
    k: Quantity,
    Zeff: Quantity,
    HR_Correction: bool = True,
) -> Quantity:
    """
    This set of hydrogenic wave functions for bound electrons taken from
    :cite:`Gregori.2004`.

    Parameters
    ----------
    n : int
        Principal quantum number
    l : int
        Azimuthal quantum number
    omega : Quantity
        Frequency shift of the scattering (unit: 1 / [time])
    k : Quantity
        Length of the scattering number (given by the scattering angle and the
        energies of the incident photons (unit: 1 / [length]).
    Zeff : Quantity
        Effective charge (unit: dimensionless)
    HR_Correction : bool, default=True
        If ``True`` the first order asymmetric correction to the impulse
        approximation will be applied.

    Returns
    -------
    J: Quantity
        Contribution of one electron in the given state to the dynamic
        bound-free structure factor (without the correction for elastic
        scattering which reduces the contribution [James.1962]).
    """
    # Find the correct _Jxx_BM function and execute it
    Jxx0 = globals()["_J{:1d}{:1d}_BM".format(n, l)](omega, k, Zeff)
    if HR_Correction:
        Jxx1 = globals()["_J{:1d}{:1d}_HR".format(n, l)](omega, k, Zeff)
        return Jxx0 + Jxx1
    return Jxx0


def J_impulse_approx(
    omega: Quantity,
    k: Quantity,
    pop: dict[int, dict[int, float]],
    Zeff: dict[int, dict[int, Quantity]],
    E_b: dict[int, Quantity],
    HR_Correction: bool = True,
) -> Quantity:
    intensity = 0 * ureg.dimensionless
    for n in pop.keys():
        for l in pop[n].keys():  # noqa E741
            intensity += (
                pop[n][l]
                * bm_bound_wavefunction(
                    n, l, omega, k, Zeff[n][l], HR_Correction
                )
                * jnp.heaviside(
                    (omega * ureg.hbar - E_b[n]).m_as(ureg.electron_volt), 0.5
                )
            )
    return intensity


def inelastic_structure_factor(
    E: Quantity,
    Eprobe: Quantity,
    angle: Quantity,
    Z_c: float,
    pop: dict[int, dict[int, float]],
    Zeff: dict[int, dict[int, Quantity]],
    E_b: dict[int, Quantity],
    J_approx: str = "impulse",
    *args,
    **kwargs,
) -> Quantity:
    """
    [Gregori.2004], eqn (20)
    """
    valid_approx = ["impulse"]
    if J_approx not in valid_approx:
        raise ValueError(
            "{} Is not an implemented approximation.\n".format(J_approx)
            + "\n"
            + "Possible options are {}".format(valid_approx)
        )

    k = thomson_momentum_transfer(Eprobe, angle)
    omega = E / ureg.hbar
    omega_0 = Eprobe / ureg.hbar

    r_k = 1 * ureg.dimensionless
    for n in pop.keys():
        for l in pop[n].keys():  # noqa E741
            r_k -= (
                pop[n][l] / Z_c * (pauling_atomic_ff(n, l, k, Zeff[n][l]) ** 2)
            )
    B = 1 + 1 / omega_0 * (ureg.hbar * k**2) / (2 * ureg.electron_mass)
    sbe = (
        r_k
        / (Z_c * B**3)
        * J_impulse_approx(omega, k, pop, Zeff, E_b, *args, **kwargs)
    )
    return sbe
