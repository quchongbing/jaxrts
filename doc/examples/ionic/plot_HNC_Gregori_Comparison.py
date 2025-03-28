"""
Compare HNC Calculations to Gregori.2006
========================================

This figure is reproducing Fig. 2 in :cite:`Schwarz.2007`, showing the notable
difference of the two approaches to the static structure factor :math:`S_{ii}`.
"""

import jax.numpy as jnp
import matplotlib.pyplot as plt

import jaxrts
from jaxrts import hnc_potentials
from jaxrts import hypernetted_chain as hnc
from jaxrts import ureg

plt.style.use("science")

fig, ax = plt.subplots()


state = jaxrts.PlasmaState(
    ions=[jaxrts.Element("Be")],
    Z_free=[2.5],
    mass_density=[
        1.21e23 / ureg.centimeter**3 * jaxrts.Element("Be").atomic_mass
    ],
    T_e=12 * ureg.electron_volt / ureg.k_B,
    T_i=[12 * ureg.electron_volt / ureg.k_B],
)


r = jnp.linspace(0.05, 1000, 2**13) * ureg.angstrom

dr = r[1] - r[0]
dk = jnp.pi / (len(r) * dr)
k = jnp.pi / r[-1] + jnp.arange(len(r)) * dk

KK = hnc_potentials.KlimontovichKraeftPotential()
Kelbg = hnc_potentials.KelbgPotential()
Coulomb = hnc_potentials.CoulombPotential()

KK.include_electrons = "SpinAveraged"
Kelbg.include_electrons = "SpinAveraged"
Coulomb.include_electrons = "SpinAveraged"

for idx, frac in enumerate([1.0, 2.0, 4.0]):
    state.T_i = jaxrts.units.to_array([state.T_e / frac])

    m = jaxrts.units.to_array([*state.atomic_masses, 1 * ureg.electron_mass])
    n = jaxrts.units.to_array([*state.n_i, state.n_e])
    T = jaxrts.units.to_array([*state.T_i, state.T_e])
    Tbar = hnc.mass_weighted_T(m, T)

    T_e_prime = jaxrts.static_structure_factors.T_cf_Greg(state.T_e, state.n_e)
    T_D = jaxrts.static_structure_factors.T_Debye_Bohm_Staver(
        T_e_prime, state.n_e, state.atomic_masses[0], state.Z_free[0]
    )
    T_i_prime = jaxrts.static_structure_factors.T_i_eff_Greg(state.T_i[0], T_D)

    V = Kelbg.short_r(state, r) * jnp.eye(2)[:, :, jnp.newaxis]
    V += -KK.full_r(state, r) * jnp.eye(2, k=1)[:, :, jnp.newaxis]
    V += -KK.full_r(state, r) * jnp.eye(2, k=-1)[:, :, jnp.newaxis]
    # Use the Coulomb - potential for the long-range part
    V_k = Coulomb.long_k(state, k) * jnp.eye(2)[:, :, jnp.newaxis]
    A = KK.full_r(state, r) * jnp.eye(2, k=-1)[:, :, jnp.newaxis]

    g, niter = hnc.pair_distribution_function_HNC(
        V, V_k, r, Tbar[:, :, jnp.newaxis], n
    )
    print(niter)
    S_ii = hnc.S_ii_HNC(k, g, n, r)

    ax.plot(
        (k * ureg.a_0).m_as(ureg.dimensionless),
        S_ii[0, 0, :].m_as(ureg.dimensionless),
        label=str(frac),
        color=f"C{idx}",
    )

    S_ii_Gregori = jaxrts.static_structure_factors.S_ii_AD(
        k, T_e_prime, T_i_prime, n[0], m[1], state.Z_free[0]
    )
    ax.plot(
        (k * ureg.a_0).m_as(ureg.dimensionless),
        S_ii_Gregori.m_as(ureg.dimensionless),
        ls="dashed",
        color=f"C{idx}",
    )
ax.set_xlim(0, 5)
ax.set_xlabel("$k [1/a_0]$")
ax.set_ylabel("S_{ii}")
ax.text(2.4, 0.02, "Solid: HNC\nDashed: Gregori.2006")
ax.legend()
plt.tight_layout()
plt.show()
