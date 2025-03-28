"""
HNC: Potentials
===============
"""

import jax.numpy as jnp
import jpu.numpy as jnpu
import matplotlib.pyplot as plt

import jaxrts
from jaxrts import ureg

plt.style.use("science")

r = jnpu.linspace(0.001 * ureg.angstrom, 10 * ureg.a0, 2**12).to(ureg.angstrom)

dr = r[1] - r[0]
dk = jnp.pi / (len(r) * dr)
k = jnp.pi / r[-1] + jnp.arange(len(r)) * dk

T = 10 * ureg.electron_volt / ureg.boltzmann_constant

Gamma = 30
di = 1 / (
    Gamma
    * (1 * ureg.boltzmann_constant)
    * T
    * 4
    * jnp.pi
    * ureg.epsilon_0
    / ureg.elementary_charge**2
)

n = (1 / (di**3 * (4 * jnp.pi / 3))).to(1 / ureg.angstrom**3)

state = jaxrts.PlasmaState(
    [jaxrts.Element("H")],
    [1],
    [n * jaxrts.Element("H").atomic_mass],
    [T],
    [T],
)

V = jaxrts.hnc_potentials.CoulombPotential()

V_l = V.long_r(state, r)
V_s = V.short_r(state, r)

V_l_k_analytical = V.long_k(state, k)
V_l_k_transformed, _ = jaxrts.hnc_potentials.transformPotential(V_l, r)

fig, ax = plt.subplots(2)
ax[0].plot(
    r.m_as(ureg.angstrom),
    V_s[0, 0, :],
    label="$V_s^C$",
)
ax[0].plot(
    r.m_as(ureg.angstrom),
    V_l[0, 0, :],
    label="$V_l^C$",
)


ax[1].plot(
    k.m_as(1 / ureg.angstrom),
    V_l_k_analytical[0, 0, :],
    label="$V_l^C$ (analytic)",
)
ax[1].plot(
    k.m_as(1 / ureg.angstrom),
    V_l_k_transformed[0, 0, :],
    label="$V_l^C$ (transformed)",
)

ax[0].set_ylim(0.01, 25)
ax[0].set_xlim(-0.01, 0.151)
ax[1].set_xlim(-0.01, 25.1)
ax[0].set_xlabel("$r$ [$\\AA$]")
ax[1].set_xlabel("$k$ [1/$\\AA$]")
ax[0].legend()
ax[1].legend()

plt.tight_layout()
plt.show()
