# Copyright 2016 Enzo Busseti, Stephen Boyd, Steven Diamond, BlackRock Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This module defines :class:`BacktestResult`.

This is the object that is returned by a market simulator's 
``backtest`` method. it contains all relevant information from
a backtest and implements the logic to compute various performance metrics,
in addition to a ``plot`` method and a rich ``__repr__`` magic method
(which is called when the user prints the object).
"""


from __future__ import annotations, print_function

import collections
from typing import Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .utils import periods_per_year_from_datetime_index

__all__ = ['BacktestResult']


# def getFiscalQuarter(dt):
#     """Convert a time to a fiscal quarter."""
#     year = dt.year
#     quarter = (dt.month - 1) // 3 + 1
#     return "Q%i %s" % (quarter, year)


class BacktestResult:
    """Store the data from a Backtest and produce metrics and plots."""

    def __init__(self, universe, trading_calendar, costs):
        """Initialization of backtest result."""
        self._h = pd.DataFrame(index=trading_calendar,
                              columns=universe, dtype=float)
        self._u = pd.DataFrame(index=trading_calendar,
                              columns=universe, dtype=float)
        self._z = pd.DataFrame(index=trading_calendar,
                              columns=universe, dtype=float)
        self.costs = {cost.__class__.__name__: pd.Series(
            index=trading_calendar, dtype=float) for cost in costs}
        self._policy_times = pd.Series(index=trading_calendar, dtype=float)
        self._simulator_times = pd.Series(index=trading_calendar, dtype=float)
        self._cash_returns = pd.Series(index=trading_calendar, dtype=float)
        self._benchmark_returns = pd.Series(
            index=trading_calendar, dtype=float)
        self._current_universe = pd.Index(universe)
        self._indexer = np.arange(len(universe), dtype=int)

    def _change_universe(self, new_universe):
        """Change current universe (columns of dataframes) during backtest."""

        # print('new universe')
        # print(new_universe)
        # print('old universe')
        # print(self._current_universe)

        # if necessary, expand columns of dataframes
        if not new_universe.isin(self._current_universe).all():

            # check that cash key didn't change!
            assert new_universe[-1] == self._current_universe[-1]

            # if new universe is larger we use it as ordering
            # this is the default situation with yfinance data
            if self._current_universe.isin(new_universe).all():
                joined = new_universe

            # otherwise we lose the ordering :(
            else: #TODO: write testcase for this
                joined = pd.Index(
                    sorted(set(self._current_universe[:-1]
                        ).union(new_universe[:-1])))
                joined.append(new_universe[-1:])

            self._h = self._h.reindex(columns = joined)
            self._u = self._u.reindex(columns = joined)
            self._z = self._z.reindex(columns = joined)

        assert new_universe.isin(self._h.columns).all()
        self._current_universe = new_universe
        self._indexer = self._h.columns.get_indexer(new_universe)

    def _log_trading(self, t: pd.Timestamp,
        h: pd.Series[float], u: pd.Series[float],
        z: pd.Series[float], costs: Dict[str, float],
        cash_return: float, benchmark_return: float or None,
        policy_time: float, simulator_time: float):
        "Log one trading period."

        if not h.index.equals(self._current_universe):
            self._change_universe(h.index)

        tidx = self._h.index.get_loc(t)

        self._h.iloc[tidx, self._indexer] = h
        self._u.iloc[tidx, self._indexer] = u
        self._z.iloc[tidx, self._indexer] = z

        for cost in costs:
            self.costs[cost].iloc[tidx] = costs[cost]

        self._simulator_times.iloc[tidx] = simulator_time
        self._policy_times.iloc[tidx] = policy_time
        self._cash_returns.iloc[tidx] = cash_return
        if benchmark_return is not None:
            self._benchmark_returns.iloc[tidx] = benchmark_return

    def _log_final(self, t, t_next, h, extra_simulator_time):
        """Log final elements and (if necessary) clean up."""

        self._h.loc[t_next] = h
        self._simulator_times.loc[t] += extra_simulator_time
        # in case of bankruptcy
        if t_next < self._h.index[-1]:
            tidx = self._h.index.get_loc(t_next)
            self._h = self._h.iloc[:tidx+1]
            self._u = self._u.iloc[:tidx]
            self._z = self._z.iloc[:tidx]
            self._simulator_times = self._simulator_times.iloc[:tidx]
            self._policy_times = self._policy_times.iloc[:tidx]
            self._cash_returns = self._cash_returns.iloc[:tidx]
            self._benchmark_returns = self._benchmark_returns.iloc[:tidx]

    #
    # General backtest information
    #

    @property
    def policy_times(self):
        """The computation time of the policy object at each period."""
        return pd.Series(self._policy_times)

    @property
    def simulator_times(self):
        """The computation time of the simulator object at each period."""
        return pd.Series(self._simulator_times)

    @property
    def cash_returns(self):
        """Per-period returns on cash (*i.e.*, the risk-free rate)."""
        return pd.Series(self._cash_returns)

    @property
    def benchmark_returns(self):
        """Benchmark returns per period (if the policy has a benchmark)."""
        return pd.Series(self._benchmark_returns)

    @property
    def cash_key(self):
        """The name of the cash unit used (e.g., USDOLLAR)."""
        return self._h.columns[-1]

    @property
    def periods_per_year(self):
        """Average trading periods per year in this backtest (rounded)."""
        return periods_per_year_from_datetime_index(self._h.index)

    #
    # Basic portfolio variables, defined in Chapter 2
    #

    @property
    def h(self):
        """The portfolio (holdings) at each trading period (including the end).
        """
        return pd.DataFrame(self._h)

    @property
    def u(self):
        """The portfolio trade vector at each trading period."""
        return pd.DataFrame(self._u)

    @property
    def z(self):
        """The portfolio trade weights at each trading period."""
        return (self.u.T / self.v).T

    @property
    def z_policy(self):
        """The trade weights requested by the policy at each trading period.

        This is different from the trade weights :math:`z` because the
        :class:`MarketSimulator` instance may change it by enforcing
        the self-financing condition (recalculates cash value), rounding
        trades to integer number of shares, canceling trades on assets whose
        volume is zero for the day, :math:`\ldots`.
        """
        return pd.DataFrame(self._z)

    @property
    def v(self):
        """The total value (or NAV) of the portfolio at each period."""
        return self.h.sum(axis=1)

    @property
    def initial_value(self):
        """The initial value (or NAV) of the portfolio."""
        return self.v.iloc[0]

    @property
    def final_value(self):
        """The portfolio value (or NAV) at the end of the back-test."""
        return self.v.iloc[-1]

    @property
    def profit(self):
        """The total profit (PnL) in this backtest."""
        return self.v.iloc[-1] - self.v.iloc[0]

    @property
    def w(self):
        """The weights of the portfolio at each period."""
        return (self.h.T / self.v).T

    @property
    def h_plus(self):
        """The post-trade portfolio (holdings) at each period."""
        return self.h.loc[self.u.index] + self.u

    @property
    def w_plus(self):
        """The post-trade weights of the portfolio at each period."""
        return (self.h_plus.T / self.v).T

    @property
    def leverage(self):
        r"""Leverage of the portfolio at each period.

        This is defined as:

        .. math::

            \| {(h_t)}_{1:n} \|_1 / v_t,

        where :math:`h_t` is the portfolio (the holdings) at time :math:`t`,
        we exclude the cash account from the :math:`\ell_1` norm,
        and :math:`v_t` is the total value (NAV) of the portfolio
        at time :math:`t`.
        """
        return np.abs(self.w.iloc[:, :-1]).sum(1)

    @property
    def turnover(self):
        r"""The turnover of the portfolio at each period.

        This is defined as:

        .. math::

            \| {(u_t)}_{1:n} \|_1 / (2 v_t),

        where :math:`u_t` are the portfolio trades at time :math:`t`,
        we exclude the cash account from the :math:`\ell_1` norm,
        and :math:`v_t` is the total value (NAV) of the portfolio
        at time :math:`t`.
        """
        return np.abs(self.u.iloc[:, :-1]).sum(axis=1) / (
            2*self.v.loc[self.u.index])

    @property
    def returns(self):
        r"""The portfolio returns at each period.

        This is defined as:

        .. math::

            R_t^\text{p} = \frac{v_{t+1} - v_t}{v_t}

        in terms of the portfolio value (NAV).
        """
        val = self.v
        return pd.Series(
            data=val.values[1:] / val.values[:-1] - 1, index=val.index[:-1]
        )

    #
    # Absolute metrics, defined in Chapter 3 Section 1
    #

    @property
    def average_return(self):
        r"""The average realized return :math:`\overline{R^\text{p}}`."""
        return np.mean(self.returns)

    @property
    def annualized_average_return(self):
        r"""The average realized return, annualized."""
        return self.average_return * self.periods_per_year

    @property
    def growth_rates(self):
        r"""The growth rate (or log-return) of the portfolio at each period.

        This is defined as:

        .. math::

            G^\text{p}_t = \log (v_{t+1} / v_t) = \log(1 + R^\text{p}_t).
        """
        return np.log(self.returns + 1)

    @property
    def average_growth_rate(self):
        r"""The average portfolio growth rate :math:`\overline{G^\text{p}}`."""
        return np.mean(self.growth_rates)

    @property
    def annualized_average_growth_rate(self):
        r"""The average portfolio growth rate, annualized."""
        return self.average_growth_rate * self.periods_per_year

    @property
    def volatility(self):
        """Realized volatility (standard deviation of the portfolio returns).
        """
        return np.std(self.returns)

    @property
    def annualized_volatility(self):
        """Realized volatility, annualized."""
        return self.volatility * np.sqrt(self.periods_per_year)

    @property
    def quadratic_risk(self):
        """Quadratic risk, square of the realized volatility."""
        return self.volatility ** 2

    @property
    def annualized_quadratic_risk(self):
        """Quadratic risk, annualized."""
        return self.quadratic_risk * self.periods_per_year

    #
    # Metrics relative to benchmark, defined in Chapter 3 Section 2
    #

    @property
    def active_returns(self):
        """Portfolio returns minus benchmark returns (if defined by policy)."""
        return self.returns - self.benchmark_returns

    @property
    def average_active_return(self):
        r"""The average active return :math:`\overline{R^\text{a}}`."""
        return np.mean(self.active_returns)

    @property
    def annualized_average_active_return(self):
        """The average active return, annualized."""
        return self.average_active_return * self.periods_per_year

    @property
    def active_volatility(self):
        """Active volatility (standard deviation of the active returns)."""
        return np.std(self.active_returns)

    @property
    def annualized_active_volatility(self):
        """Annualized active volatility."""
        return self.active_volatility * np.sqrt(self.periods_per_year)

    @property
    def excess_returns(self):
        """Excess portfolio returns with respect to the cash returns."""
        return self.returns - self.cash_returns

    @property
    def average_excess_return(self):
        r"""The average excess return :math:`\overline{R^\text{e}}`."""
        return np.mean(self.excess_returns)

    @property
    def annualized_average_excess_return(self):
        """The average excess return, annualized."""
        return self.average_excess_return * self.periods_per_year

    @property
    def excess_volatility(self):
        """Excess volatility (standard deviation of the excess returns)."""
        return np.std(self.excess_returns)

    @property
    def annualized_excess_volatility(self):
        """Annualized excess volatility."""
        return self.excess_volatility * np.sqrt(self.periods_per_year)

    @property
    def sharpe_ratio(self):
        r"""Sharpe ratio (using annualized excess portfolio returns).

        This is defined as

        .. math::

            \text{SR} = \overline{R^\text{e}}/\sigma^\text{e}

        where :math:`\overline{R^\text{e}}` is the average excess portfolio
        return and :math:`\sigma^\text{e}` its standard deviation. Both are
        annualized.
        """
        return self.annualized_average_excess_return / (
            self.annualized_excess_volatility + 1E-8)

    @property
    def information_ratio(self):
        r"""Information ratio (using annualized active portfolio returns).

        This is defined as

        .. math::

            \text{IR} = \overline{R^\text{a}}/\sigma^\text{a}

        where :math:`\overline{R^\text{a}}` is the average active portfolio
        return and :math:`\sigma^\text{a}` its standard deviation. Both are
        annualized.
        """
        return self.annualized_average_active_return / (
            self.annualized_active_volatility + 1E-8)

    @property
    def excess_growth_rates(self):
        r"""The growth rate of the portfolio, relative to cash.
        
        This is defined as:
        
        .. math::

            G^\text{e}_t = \log(1 + R^\text{e}_t)

        where :math:`R^\text{e}_t` are the excess portfolio returns.
        """
        return np.log(self.excess_returns + 1)

    @property
    def active_growth_rates(self):
        r"""The growth rate of the portfolio, relative to benchmark.
        
        This is defined as:
        
        .. math::

            G^\text{a}_t = \log(1 + R^\text{a}_t)

        where :math:`R^\text{a}_t` are the active portfolio returns.
        """
        return np.log(self.active_returns + 1)

    @property
    def average_excess_growth_rate(self):
        r"""The average excess growth rate :math:`\overline{G^\text{e}}`."""
        return np.mean(self.excess_growth_rates)

    @property
    def annualized_average_excess_growth_rate(self):
        """The average excess growth rate, annualized."""
        return self.average_excess_growth_rate * self.periods_per_year

    @property
    def average_active_growth_rate(self):
        r"""The average active growth rate :math:`\overline{G^\text{a}}`."""
        return np.mean(self.active_growth_rates)

    @property
    def annualized_average_active_growth_rate(self):
        """The average active growth rate, annualized."""
        return self.average_active_growth_rate * self.periods_per_year

    @property
    def drawdown(self):
        """The drawdown of the portfolio value over time."""
        return -(1 - (self.v / self.v.cummax()))

    # TODO: decide if keeping any of these or throw

    # @staticmethod
    # def _print_growth_rate(gr):
    #     """Transform growth rate into return and pretty-print it.
    #
    #     Either prints in basis points, percentage, or multiplication.
    #     """
    #     ret = np.exp(gr)-1
    #     if np.abs(ret) < 0.005:
    #         return f'{int(ret*1E4):d}bp'
    #     if np.abs(gr) < 1:
    #         return f'{ret*100:.2f}%'
    #     return f'{1+ret:.1f}X'

    #
    # def _growth_to_return(self, growth_rates):
    #     """Convert growth to annualized percentage return."""
    #     return 100 * (np.exp(self.PPY * growth) - 1)

    # def get_quarterly_returns(self, benchmark=None):
    #     """The annualized returns for each fiscal quarter."""
    #     ret = self.growth_rates
    #     quarters = ret.groupby(getFiscalQuarter).aggregate(np.mean)
    #     return self._growth_to_return(quarters)
    #
    # def get_best_quarter(self, benchmark=None):
    #     ret = self.get_quarterly_returns(benchmark)
    #     return (ret.argmax(), ret.max())
    #
    # def get_worst_quarter(self, benchmark=None):
    #     ret = self.get_quarterly_returns(benchmark)
    #     return (ret.argmin(), ret.min())

    # @property
    # def trading_days(self):
    #     """The fraction of days with nonzero turnover."""
    #     return (self.turnover.values > 0).sum() / self.turnover.size

    #
    # Results presentation
    #

    def plot(self, show=True, how_many_weights=7):
        """Make plot and show it.

        :param show: if True, call ``matplotlib.Figure.show``, helpful when
            running in the interpreter.
        :type show: bool
        :param how_many_weights: How many assets' weights are shown in the
            weights plots. The ones with largest average absolute value
            are chosen.
        :type how_many_weights: int
        """

        # US Letter size
        fig, axes = plt.subplots(3, figsize=(8.5, 11), layout='constrained')
        fig.suptitle('Back-test result')

        # value
        self.v.plot(label='Portfolio value', ax=axes[0])
        axes[0].set_ylabel(self.cash_key)
        axes[0].set_yscale('log')
        axes[0].legend()
        axes[0].grid(True, linestyle='--', which="both")

        # weights
        biggest_weights = np.abs(self.w).mean(
            ).sort_values().iloc[-how_many_weights:].index
        self.w[biggest_weights].plot(ax=axes[1])
        axes[1].set_ylabel(f'Largest {how_many_weights} weights')
        axes[1].grid(True, linestyle='--')

        # leverage / turnover
        self.leverage.plot(ax=axes[2], linestyle='--',
                           color='k', label='Leverage')
        self.turnover.plot(ax=axes[2], linestyle='-',
                           color='r', label='Turnover')
        axes[2].legend()
        axes[2].grid(True, linestyle='--')

        if show:
            fig.show()

    def __repr__(self):
        """Print the class instance."""

        stats = collections.OrderedDict({
            "Universe size": self.h.shape[1],
            "Initial timestamp": self.h.index[0],
            "Final timestamp": self.h.index[-1],
            "Number of periods": self.u.shape[0],
            f"Initial value ({self.cash_key})": f"{self.initial_value:.3e}",
            f"Final value ({self.cash_key})": f"{self.final_value:.3e}",
            f"Profit ({self.cash_key})": f"{self.profit:.3e}",
            ' '*4: '',
            "Avg. return (annualized)":
                f"{100 * self.annualized_average_return:.1f}%",
            "Volatility (annualized)":
                f"{100 * self.annualized_volatility:.1f}%",
            "Avg. excess return (annualized)":
                f"{100 * self.annualized_average_excess_return:.1f}%",
            "Avg. active return (annualized)":
                f"{100 * self.annualized_average_active_return:.1f}%",
            "Excess volatility (annualized)":
                f"{100 * self.annualized_excess_volatility:.1f}%",
            "Active volatility (annualized)":
                f"{100 * self.annualized_active_volatility:.1f}%",
            ' '*5: '',
            "Avg. growth rate (annualized)":
                f"{100*self.annualized_average_growth_rate:.1f}%",
            "Avg. excess growth rate (annualized)":
                f"{100*self.annualized_average_excess_growth_rate:.1f}%",
            "Avg. active growth rate (annualized)":
                f"{100*self.annualized_average_active_growth_rate:.1f}%",
        })

        if len(self.costs):
            stats[' '*6] = ''
        for cost in self.costs:
            stats[f'Avg. {cost}'] = \
                f"{(self.costs[cost]/self.v).mean()*1E4:.0f}bp"
            stats[f'Max. {cost}'] = \
                f"{(self.costs[cost]/self.v).max()*1E4:.0f}bp"

        stats.update(collections.OrderedDict({
            ' '*7: '',
            "Sharpe ratio": f"{self.sharpe_ratio:.2f}",
            "Information ratio": f"{self.information_ratio:.2f}",
            ' '*8: '',
            "Avg. drawdown": f"{self.drawdown.mean() * 100:.1f}%",
            "Min. drawdown": f"{self.drawdown.min() * 100:.1f}%",
            "Avg. leverage": f"{self.leverage.mean() * 100:.1f}%",
            "Max. leverage": f"{self.leverage.max() * 100:.1f}%",
            "Avg. turnover": f"{self.turnover.mean() * 100:.1f}%",
            "Max. turnover": f"{self.turnover.max() * 100:.1f}%",
            ' '*9: '',
            "Avg. policy time": f"{self.policy_times.mean():.3f}s",
            "Avg. simulator time": f"{self.simulator_times.mean():.3f}s",
            "Total time":
                f"{self.simulator_times.sum() + self.policy_times.sum():.3f}s",
            }))

        if np.all(np.isnan(self.active_returns)):
            del stats["Avg. active return (annualized)"]
            del stats["Active volatility (annualized)"]
            del stats["Avg. active growth rate (annualized)"]
            del stats["Information ratio"]

        content = pd.Series(stats).to_string()
        lenline = len(content.split('\n')[0])

        return '\n' + '#'*lenline + '\n' + content + '\n' + '#'*lenline + '\n'
