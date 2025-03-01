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
"""Unit tests for the market simulator and its backtest methods."""

import multiprocessing
import os
import time
import unittest
from copy import deepcopy

import numpy as np
import pandas as pd

import cvxportfolio as cvx
from cvxportfolio.errors import *
from cvxportfolio.estimator import DataEstimator
from cvxportfolio.simulator import (DownloadedMarketData, MarketSimulator,
                                    StockMarketSimulator,
                                    UserProvidedMarketData)
from cvxportfolio.tests import CvxportfolioTest


class TestSimulator(CvxportfolioTest):
    """Test MarketSimulator and assorted end-to-end tests."""

    def test_simulator_raises(self):
        """Test syntax checker of MarketSimulator."""

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator()

        with self.assertRaises(SyntaxError):
            simulator = StockMarketSimulator(returns=pd.DataFrame(
                [[0.]], index=[pd.Timestamp.today()], columns=['USDOLLAR']))

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator(volumes=pd.DataFrame(
                [[0.]], index=[pd.Timestamp.today()]))

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator(returns=pd.DataFrame(
                [[0.]], columns=['USDOLLAR'], index=[pd.Timestamp.today()]),
                    volumes=pd.DataFrame([[0.]]))

        # not raises
        simulator = MarketSimulator(returns=pd.DataFrame([[0., 0.]],
            columns=['A', 'USDOLLAR']), volumes=pd.DataFrame(
            [[0.]], columns=['A']), round_trades=False)

        with self.assertRaises(SyntaxError):
            simulator = MarketSimulator(returns=pd.DataFrame(
                [[0., 0.]], index=[pd.Timestamp.today()],
                columns=['X', 'USDOLLAR']),
                volumes=pd.DataFrame([[0.]]))

    def test_prepare_data(self):
        simulator = MarketSimulator(['ZM', 'META'], base_location=self.datadir)
        self.assertTrue(simulator.market_data.returns.shape[1] == 3)
        self.assertTrue(simulator.market_data.prices.shape[1] == 2)
        self.assertTrue(simulator.market_data.volumes.shape[1] == 2)
        # self.assertTrue( simulator.sigma_estimate.data.shape[1] == 2)
        self.assertTrue(np.isnan(simulator.market_data.returns.iloc[-1, 0]))
        self.assertTrue(np.isnan(simulator.market_data.volumes.iloc[-1, 1]))
        self.assertTrue(not np.isnan(simulator.market_data.prices.iloc[-1, 0]))
        self.assertTrue(
            simulator.market_data.returns.index[-1]
            == simulator.market_data.volumes.index[-1])
        self.assertTrue(
            simulator.market_data.returns.index[-1]
            == simulator.market_data.prices.index[-1])

    def test_holding_cost(self):
        """Test the simulator interface of cvx.HoldingCost."""

        t = self.returns.index[-20]

        cash_return = self.returns.loc[t, 'cash']

        # stock holding cost
        for i in range(10):
            np.random.seed(i)
            h_plus = np.random.randn(4)*10000
            h_plus[3] = 10000 - sum(h_plus[:-1])
            h_plus = pd.Series(h_plus)

            dividends = np.random.uniform(size=len(h_plus)-1) * 1E-4

            hcost = cvx.HoldingCost(short_fees=5, dividends=dividends)

            sim_hcost = hcost.simulate(
                t=t, h_plus=h_plus,
                t_next=t + pd.Timedelta('1d'))

            hcost = -(np.exp(np.log(1.05)/365.24)-1) * sum(
                -np.minimum(h_plus, 0.)[:-1])
            hcost += dividends @ h_plus[:-1]
            print(hcost, -sim_hcost)
            self.assertTrue(np.isclose(hcost, -sim_hcost))

    def test_transaction_cost_syntax(self):

        t = self.returns.index[-20]

        past_returns, current_returns, past_volumes, current_volumes, \
            current_prices = self.market_data.serve(t)

        u = pd.Series(np.ones(len(current_prices)+1), self.universe)

        tcost = cvx.StocksTransactionCost()
        # syntax checks
        with self.assertRaises(SyntaxError):
            tcost.simulate(t, u=u,
                            past_returns=past_returns,
                            current_returns=current_returns,
                            past_volumes=past_volumes,
                            current_volumes=current_volumes,
                            current_prices=None)

        tcost = cvx.TransactionCost(pershare_cost=None,)
        tcost.simulate(t, u=u, current_prices=None,
                        past_returns=past_returns,
                        current_returns=current_returns,
                        past_volumes=past_volumes,
                        current_volumes=current_volumes)

        tcost = cvx.TransactionCost()
        with self.assertRaises(SyntaxError):
            tcost.simulate(t, u=u, current_prices=current_prices,
                            past_returns=past_returns,
                            current_returns=current_returns,
                            past_volumes=None,
                            current_volumes=None)

        tcost = cvx.TransactionCost(b=None)
        tcost.simulate(t, u=u, current_prices=current_prices,
                        past_returns=past_returns,
                        current_returns=current_returns,
                        past_volumes=None,
                        current_volumes=None)

    def test_transaction_cost(self):

        t = self.returns.index[-5]

        past_returns, current_returns, past_volumes, current_volumes, \
            current_prices = self.market_data.serve(t)

        # print(current_prices)

        n = len(current_prices)

        for i in range(10):
            np.random.seed(i)
            spreads = np.random.uniform(size=n)*1E-3
            u = np.random.uniform(size=n+1)*1E4
            u[-1] = -sum(u[:-1])
            u = pd.Series(u, self.universe)
            u = MarketSimulator._round_trade_vector(u, current_prices)

            tcost = cvx.StocksTransactionCost(a=spreads/2)

            sim_cost = tcost.simulate(
                t, u=u, current_prices=current_prices,
                past_returns=past_returns,
                current_returns=current_returns,
                past_volumes=past_volumes,
                current_volumes=current_volumes)

            shares = sum(np.abs(u[:-1] / current_prices))
            tcost = -0.005 * shares
            # print(tcost, sim_cost)
            tcost -= np.abs(u.iloc[:-1]) @ spreads / 2
            # print(self.returns.loc[self.returns.index <= t].iloc[-252:, :-1].std())
            tcost -= sum((np.abs(u.iloc[:-1])**1.5
                ) * self.returns.loc[self.returns.index <=
                t].iloc[-252:, :-1].std(ddof=0) / np.sqrt(self.volumes.loc[t]))
            # sim_tcost = simulator.transaction_costs(u)
            #
            print(tcost, sim_cost)
            self.assertTrue(np.isclose(tcost, -sim_cost))

    def test_methods(self):
        """Test some methods of MarketSimulator."""
        simulator = MarketSimulator(
            ['ZM', 'META', 'AAPL'], base_location=self.datadir)

        self.strip_tz_and_hour(simulator.market_data)

        # , pd.Timestamp('2022-04-11')]: # can't because sigma requires 1000 days
        for t in [pd.Timestamp('2023-04-13')]:
            # super(simulator.__class__, simulator).values_in_time_recursive(t=t)

            # round trade

            for i in range(10):
                np.random.seed(i)
                tmp = np.random.uniform(size=4)*1000
                tmp[3] = -sum(tmp[:3])
                u = pd.Series(tmp, simulator.market_data.full_universe)
                rounded = simulator._round_trade_vector(
                    u, simulator.market_data.prices.loc[t])
                self.assertTrue(sum(rounded) == 0)
                self.assertTrue(
                    np.linalg.norm(rounded[:-1] - u[:-1])
                    < np.linalg.norm(simulator.market_data.prices.loc[t]/2))

                print(u)

    @staticmethod
    def strip_tz_and_hour(market_data):
        market_data.returns.index = \
            market_data.returns.index.tz_localize(None).floor("D")
        market_data.volumes.index = \
            market_data.volumes.index.tz_localize(None).floor("D")
        market_data.prices.index = \
            market_data.prices.index.tz_localize(None).floor("D")

    def test_simulate_policy(self):
        """Test basic policy simulation."""
        simulator = StockMarketSimulator(
            ['META', 'AAPL'], base_location=self.datadir)

        # to fix this test
        self.strip_tz_and_hour(simulator.market_data)

        start_time = '2023-03-10'
        end_time = '2023-04-20'

        # hold
        policy = cvx.Hold()
        for i in range(10):
            np.random.seed(i)
            h = np.random.randn(3)*10000
            h[-1] = 10000 - sum(h[:-1])
            h0 = pd.Series(h, simulator.market_data.full_universe)
            h = pd.Series(h0, copy=True)

            policy.initialize_estimator_recursive(
                universe=simulator.market_data.full_universe,
                trading_calendar=simulator.market_data.trading_calendar(
                    start_time, end_time, include_end=False)
            )

            for (i, t) in enumerate(simulator.market_data.returns.index[
                    (simulator.market_data.returns.index >= start_time) & (
                    simulator.market_data.returns.index <= end_time)]):
                t_next = simulator.market_data.returns.index[i+1]
                oldcash = h.iloc[-1]
                past_returns, current_returns, past_volumes, current_volumes, \
                    current_prices = simulator.market_data.serve(t)
                h, z, u, costs, timer = simulator.simulate(
                    t=t, h=h, policy=policy, t_next=t_next,
                    past_returns=past_returns, current_returns=current_returns,
                    past_volumes=past_volumes, current_volumes=current_volumes,
                    current_prices=current_prices)
                tcost, hcost = costs['StocksTransactionCost'
                    ], costs['StocksHoldingCost']
                assert tcost == 0.
                # if np.all(h0[:2] > 0):
                #    assert hcost == 0.
                assert np.isclose(
                    (oldcash - hcost) * (1+simulator.market_data.returns.loc[
                        t, 'USDOLLAR']), h.iloc[-1])

            simh = h0[:-1] * simulator.market_data.prices.loc[pd.Timestamp(
                end_time) + pd.Timedelta('1d')
                ] / simulator.market_data.prices.loc[start_time]
            self.assertTrue(np.allclose(simh, h[:-1]))

        # proportional_trade
        policy = cvx.ProportionalTradeToTargets(
            targets=pd.DataFrame({pd.Timestamp(end_time)
                + pd.Timedelta('1d'):  pd.Series([0, 0, 1],
                simulator.market_data.returns.columns)}).T)

        for i in range(10):
            np.random.seed(i)
            h = np.random.randn(3)*10000
            h[-1] = 10000 - sum(h[:-1])
            h0 = pd.Series(h, simulator.market_data.returns.columns)
            h = pd.Series(h0, copy=True)
            policy.initialize_estimator_recursive(
                universe=simulator.market_data.full_universe,
                trading_calendar=simulator.market_data.trading_calendar(
                    start_time, end_time, include_end=False)
            )

            for i, t in enumerate(simulator.market_data.returns.index[
                    (simulator.market_data.returns.index >= start_time) &
                        (simulator.market_data.returns.index <= end_time)]):
                t_next = simulator.market_data.returns.index[i+1]
                oldcash = h.iloc[-1]
                past_returns, current_returns, past_volumes, current_volumes, \
                    current_prices = simulator.market_data.serve(t)
                h, z, u, costs, timer = simulator.simulate(
                    t=t, h=h, policy=policy, t_next=t_next,
                    past_returns=past_returns, current_returns=current_returns,
                    past_volumes=past_volumes, current_volumes=current_volumes,
                    current_prices=current_prices)
                tcost, hcost = costs['StocksTransactionCost'
                    ], costs['StocksHoldingCost']
                print(h)
                # print(tcost, stock_hcost, cash_hcost)

            self.assertTrue(
                np.all(np.abs(h[:-1])
                    < simulator.market_data.prices.loc[end_time]))

    def test_backtest(self):
        pol = cvx.SinglePeriodOptimization(cvx.ReturnsForecast() -
                                           cvx.ReturnsForecastError() -
                                           .5 * cvx.FullCovariance(),
                                           [  # cvx.LongOnly(),
            cvx.LeverageLimit(1)], verbose=True)
        sim = cvx.MarketSimulator(['AAPL', 'MSFT'],  # ', 'GE', 'CVX', 'XOM', 'AMZN', 'ORCL', 'WMT', 'HD', 'DIS', 'MCD', 'NKE']
                                  base_location=self.datadir)
        result = sim.backtest(pol, pd.Timestamp(
            '2023-01-01'), pd.Timestamp('2023-04-20'))

        print(result)

    def test_backtest_concatenation(self):
        sim = cvx.MarketSimulator(['AAPL', 'ZM'], base_location=self.datadir)
        pol = cvx.SinglePeriodOptimization(cvx.ReturnsForecast() -
                                           cvx.ReturnsForecastError() -
                                           .5 * cvx.FullCovariance(),
                                           [  # cvx.LongOnly(),
            cvx.LeverageLimit(1)], verbose=True)

        result = sim.backtest(pol, pd.Timestamp(
            '2020-04-01'), pd.Timestamp('2020-05-01'))  # zoom enters in mid-april
        ridx = result.w.index
        self.assertTrue(result.w['ZM'].isnull().sum() > 5)
        self.assertTrue(result.w['AAPL'].isnull().sum() < 2)
        self.assertTrue(len(ridx) == len(set(ridx)))
        self.assertTrue(len(ridx) == len(sim.market_data.returns.loc[
            (sim.market_data.returns.index >= ridx[0]) & (
            sim.market_data.returns.index <= ridx[-1])]))
        print(result)

    def test_multiple_backtest(self):

        pol = cvx.SinglePeriodOptimization(cvx.ReturnsForecast() -
                                           cvx.ReturnsForecastError() -
                                           .5 * cvx.FullCovariance(),
                                           [  # cvx.LongOnly(),
            cvx.LeverageLimit(1)], verbose=True)

        pol1 = cvx.Uniform()

        sim = cvx.MarketSimulator(['AAPL', 'MSFT'],  # ', 'GE', 'CVX', 'XOM', 'AMZN', 'ORCL', 'WMT', 'HD', 'DIS', 'MCD', 'NKE']
                                  base_location=self.datadir)

        with self.assertRaises(SyntaxError):
            result = sim.backtest_many([pol, pol1], pd.Timestamp(
                '2023-01-01'), pd.Timestamp('2023-04-20'), h=['hello'])

        result = sim.backtest(pol1, pd.Timestamp(
            '2023-01-01'), pd.Timestamp('2023-04-20'))

        result2, result3 = sim.backtest_many(
            [pol, pol1], pd.Timestamp('2023-01-01'), pd.Timestamp('2023-04-20'))

        self.assertTrue(np.all(result.h == result3.h))

    def test_multiple_backtest2(self):
        """Test re-use of a worker process."""
        cpus = multiprocessing.cpu_count()

        sim = cvx.MarketSimulator(['AAPL', 'MSFT'], base_location=self.datadir)
        pols = [cvx.SinglePeriodOptimization(cvx.ReturnsForecast()
            - 1 * cvx.FullCovariance(), [cvx.LeverageLimit(1)])
                for i in range(cpus*2)]
        results = sim.backtest_many(pols, pd.Timestamp(
            '2023-01-01'), pd.Timestamp('2023-01-15'), parallel=True)
        sharpes = [result.sharpe_ratio for result in results]
        self.assertTrue(len(set(sharpes)) == 1)

    def test_multiple_backtest3(self):
        """Test benchmarks."""

        sim = cvx.MarketSimulator(['AAPL', 'MSFT'], base_location=self.datadir)
        pols = [
            cvx.SinglePeriodOptimization(cvx.ReturnsForecast(
            ) - 1 * cvx.FullCovariance(), [cvx.LeverageLimit(1)]),
            cvx.SinglePeriodOptimization(cvx.ReturnsForecast(
            ) - 1 * cvx.FullCovariance(), [cvx.LeverageLimit(1)],
                benchmark=cvx.Uniform),
            cvx.SinglePeriodOptimization(cvx.ReturnsForecast(
            ) - 1 * cvx.FullCovariance(), [cvx.LeverageLimit(1)],
                benchmark=cvx.MarketBenchmark),
        ]
        results = sim.backtest_many(pols, pd.Timestamp(
            '2023-01-01'), pd.Timestamp('2023-01-15'), parallel=True)
        print(np.linalg.norm(results[0].w.sum()[:2] - .5))
        print(np.linalg.norm(results[1].w.sum()[:2] - .5))
        print(np.linalg.norm(results[2].w.sum()[:2] - .5))
        self.assertTrue(np.linalg.norm(results[1].w.sum()[
                        :2] - .5) < np.linalg.norm(
                        results[0].w.sum()[:2] - .5))
        self.assertTrue(np.linalg.norm(results[1].w.sum()[
                        :2] - .5) < np.linalg.norm(
                        results[2].w.sum()[:2] - .5))

    def test_multiple_backtest4(self):
        """Test _downsample and offline cache."""

        time_first = 0.
        results_first = []
        for downsampling in ['weekly', 'monthly', 'quarterly', 'annual']:
            sim = cvx.MarketSimulator(['AAPL', 'MSFT', 'GE', 'ZM', 'META'],
                                      base_location=self.datadir, trading_frequency=downsampling)
            pol = cvx.SinglePeriodOptimization(cvx.ReturnsForecast(
            ) - 1 * cvx.FullCovariance() - cvx.TransactionCost(exponent=1.5), [cvx.LeverageLimit(1)])
            s = time.time()
            results_first.append(sim.backtest(pol, pd.Timestamp('2020-12-01')))
            print(results_first[-1])
            time_first += time.time() - s

        time_second = 0.
        results_second = []
        for downsampling in ['weekly', 'monthly', 'quarterly', 'annual']:
            sim = cvx.MarketSimulator(['AAPL', 'MSFT', 'GE', 'ZM', 'META'],
                                      base_location=self.datadir, trading_frequency=downsampling)
            pol = cvx.SinglePeriodOptimization(cvx.ReturnsForecast(
            ) - 1 * cvx.FullCovariance() - cvx.TransactionCost(exponent=1.5), [cvx.LeverageLimit(1)])
            s = time.time()
            results_second.append(sim.backtest(
                pol, pd.Timestamp('2020-12-01')))
            print(results_second[-1])
            time_second += time.time() - s

        # example is too small to see speed difference w/ cache
        # sadly we have to drop this test element
        # self.assertTrue(time_second < time_first)
        print(time_second, time_first)
        [self.assertTrue(np.isclose(results_first[i].sharpe_ratio,
                         results_second[i].sharpe_ratio)) for i in range(len(results_first))]

    def test_result(self):
        """Test methods and properties of result."""
        sim = cvx.MarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'ZM', 'META'], base_location=self.datadir)
        result = sim.backtest(cvx.Uniform(), pd.Timestamp(
            '2023-01-01'))
        result.plot(show=False)
        print(result)
        for attribute in dir(result):
            print(attribute, getattr(result, attribute))

    def test_spo_benchmark(self):
        """Test the effect of benchmark on SPO policies."""

        sim = cvx.MarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'ZM', 'META'], trading_frequency='monthly', base_location=self.datadir)

        objective = cvx.ReturnsForecast() - 10 * cvx.FullCovariance()
        constraints = [cvx.LongOnly(), cvx.LeverageLimit(1)]

        myunif = pd.Series(0.2, ['AAPL', 'MSFT', 'GE', 'ZM', 'META'])
        myunif['USDOLLAR'] = 0.

        policies = [cvx.SinglePeriodOptimization(objective, constraints, benchmark=bm)
                    for bm in [cvx.AllCash(), cvx.Uniform(), cvx.MarketBenchmark(),
                               myunif]]

        results = sim.backtest_many(policies, start_time='2023-01-01',
                                    parallel=False)  # important for test coverage!!

        # check myunif is the same as uniform
        self.assertTrue(np.isclose(
            results[1].sharpe_ratio, results[3].sharpe_ratio))

        # check cash benchmark sol has higher cash weights
        self.assertTrue(results[0].w.USDOLLAR.mean() >=
                        results[1].w.USDOLLAR.mean())
        self.assertTrue(results[0].w.USDOLLAR.mean() >=
                        results[2].w.USDOLLAR.mean())

        # check that uniform bm sol is closer to uniform alloc than market bm sol
        norm_smaller = ((results[1].w.iloc[:, :-1] - 0.2) **
                        2).mean(1) < ((results[2].w.iloc[:, :-1] - 0.2)**2).mean(1)
        print(norm_smaller.describe())
        self.assertTrue(norm_smaller.mean() > .5)

    def test_market_neutral(self):
        """Test SPO with market neutral constraint."""

        sim = cvx.MarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'GOOG', 'META', 'GLD'],
            trading_frequency='monthly', base_location=self.datadir)

        objective = cvx.ReturnsForecast() - 2 * cvx.FullCovariance()

        policies = [cvx.SinglePeriodOptimization(objective, co) for co in [
            [], [cvx.MarketNeutral()], [cvx.DollarNeutral()]]]

        results = sim.backtest_many(policies, start_time='2023-01-01',
                                    parallel=False)  # important for test coverage
        print(results)

        # check that market neutral sol is closer to
        dists_from_dollar_neutral = [
            np.abs(result.w.iloc[:, -1] - 1).mean() for result in results]
        print('dists_from_dollar_neutral')
        print(dists_from_dollar_neutral)
        self.assertTrue(
            dists_from_dollar_neutral[2] < dists_from_dollar_neutral[1])
        self.assertTrue(
            dists_from_dollar_neutral[1] < dists_from_dollar_neutral[0])

    def test_timed_constraints(self):
        """Test some constraints that depend on time."""

        sim = cvx.StockMarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'META'],
            trading_frequency='monthly', base_location=self.datadir)

        # cvx.NoTrade
        objective = cvx.ReturnsForecast() - 2 * cvx.FullCovariance()

        no_trade_ts = [sim.market_data.returns.index[-2],
                       sim.market_data.returns.index[-6]]

        policy = cvx.SinglePeriodOptimization(
            objective, [cvx.NoTrade('AAPL', no_trade_ts)])

        result = sim.backtest(policy, start_time='2023-01-01')
        print(result.z)
        for t in no_trade_ts:
            self.assertTrue(np.isclose(result.z['AAPL'].loc[t], 0., atol=1E-3))

        # cvx.MinWeightsAtTimes, cvx.MaxWeightsAtTimes
        policies = [cvx.MultiPeriodOptimization(
            objective - cvx.StocksTransactionCost(),
            [cvx.MinWeightsAtTimes(0., no_trade_ts),
            cvx.MaxWeightsAtTimes(0., no_trade_ts)],
            planning_horizon=p) for p in [1, 3, 5]]

        results = sim.backtest_many(
            policies, start_time='2023-01-01', initial_value=1E6,
            parallel=False)  # important for test coverage
        print(results)

        total_tcosts = [result.costs['StocksTransactionCost'].sum()
                        for result in results]
        print(total_tcosts)
        self.assertTrue(total_tcosts[0] > total_tcosts[1])
        self.assertTrue(total_tcosts[1] > total_tcosts[2])

    def test_eq_soft_constraints(self):
        """We check that soft DollarNeutral penalizes non-dollar-neutrality."""

        sim = cvx.StockMarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'ZM', 'META'],
            trading_frequency='monthly', base_location=self.datadir)

        objective = cvx.ReturnsForecast() - 5 * cvx.FullCovariance()

        policies = [cvx.SinglePeriodOptimization(
            objective - cvx.SoftConstraint(cvx.DollarNeutral()) * gamma)
            for gamma in [.0001, .001, .01]]
        policies.append(cvx.SinglePeriodOptimization(
            objective, [cvx.DollarNeutral()]))
        results = sim.backtest_many(policies, start_time='2023-01-01',
                                    parallel=False)  # important for test coverage
        print(results)
        allcashpos = [((res.w.iloc[:, -1]-1)**2).mean() for res in results]
        print(allcashpos)
        self.assertTrue(allcashpos[0] > allcashpos[1])
        self.assertTrue(allcashpos[1] > allcashpos[2])
        self.assertTrue(allcashpos[2] > allcashpos[3])

    def test_ineq_soft_constraints(self):
        """We check that soft LongOnly penalizes shorts."""

        sim = cvx.StockMarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'ZM', 'META'],
            trading_frequency='monthly', base_location=self.datadir)

        objective = cvx.ReturnsForecast() - .5 * cvx.FullCovariance()

        policies = [cvx.SinglePeriodOptimization(
            objective - cvx.SoftConstraint(cvx.LongOnly()) * gamma,
            [cvx.MarketNeutral()]) for gamma in [.0001, .001, .01]]
        policies.append(cvx.SinglePeriodOptimization(
            objective, [cvx.LongOnly(), cvx.MarketNeutral()]))
        results = sim.backtest_many(policies, start_time='2023-01-01',
                                    parallel=False)  # important for test coverage
        print(results)
        allshorts = [np.minimum(res.w.iloc[:, :-1], 0.).sum().sum()
                     for res in results]
        print(allshorts)
        self.assertTrue(allshorts[0] < allshorts[1])
        self.assertTrue(allshorts[1] < allshorts[2])
        self.assertTrue(allshorts[2] < allshorts[3])

    def test_cost_constraints(self):
        """We check that cost constraints work as expected."""

        sim = cvx.StockMarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'ZM', 'META'],
            trading_frequency='monthly', base_location=self.datadir)

        policies = [
            cvx.SinglePeriodOptimization(cvx.ReturnsForecast(), [
                                         cvx.FullCovariance() <= el**2])
            for el in [0.01, .02, .05, .1]]

        results = sim.backtest_many(policies, start_time='2023-01-01',
                                    parallel=False)  # important for test coverage
        print(results)

        self.assertTrue(results[0].volatility < results[1].volatility)
        self.assertTrue(results[1].volatility < results[2].volatility)
        self.assertTrue(results[2].volatility < results[3].volatility)

    def test_dcp_convex_raises(self):

        sim = cvx.StockMarketSimulator(
            ['AAPL'], base_location=self.datadir)

        policy = cvx.SinglePeriodOptimization(
            cvx.ReturnsForecast(), [cvx.FullCovariance() >= 2])

        with self.assertRaises(ConvexSpecificationError):
            sim.backtest(policy)

        policy = cvx.SinglePeriodOptimization(
            cvx.ReturnsForecast() + .5 * cvx.FullCovariance())

        with self.assertRaises(ConvexityError):
            sim.backtest(policy)

    def test_hyperparameters_optimize(self):
        """Test hyperparameter optimization."""

        GAMMA_RISK = cvx.Gamma()
        GAMMA_TRADE = cvx.Gamma()
        objective = cvx.ReturnsForecast() - GAMMA_RISK * cvx.FullCovariance()\
             - GAMMA_TRADE * cvx.StocksTransactionCost()
        policy = cvx.SinglePeriodOptimization(
            objective, [cvx.LongOnly(), cvx.LeverageLimit(1)])

        simulator = cvx.StockMarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'ZM', 'META'],
            trading_frequency='monthly',
            base_location=self.datadir)

        self.assertTrue(GAMMA_RISK.current_value == 1.)
        self.assertTrue(GAMMA_TRADE.current_value == 1.)

        simulator.optimize_hyperparameters(
            policy, start_time='2023-01-01', end_time='2023-10-01')

        self.assertTrue(np.isclose(GAMMA_RISK.current_value, 1.4641))
        self.assertTrue(np.isclose(GAMMA_TRADE.current_value, 0.385543289))

    def test_cancel_trades(self):
        """Test trade cancellation."""

        sim = cvx.StockMarketSimulator(
            ['AAPL', 'ZM'],
            trading_frequency='monthly',
            base_location=self.datadir)

        sim.market_data.volumes['ZM'] = 0.

        objective = cvx.ReturnsForecast() - 5 * cvx.FullCovariance()
        policy = cvx.SinglePeriodOptimization(
            objective, [cvx.LongOnly(), cvx.LeverageLimit(1)])

        sim.backtest(policy, start_time='2023-01-01')

    def test_svd_covariance_forecaster(self):
        """Test SVD covariance forecaster in simulation."""

        sim = cvx.StockMarketSimulator(
            ['AAPL', 'MSFT', 'GE', 'ZM', 'META', 'GOOG', 'GLD'],
            trading_frequency='quarterly',
            base_location=self.datadir)

        objective = cvx.ReturnsForecast() - 5 * cvx.FactorModelCovariance(
            num_factors=2, Sigma=None)
        policy = cvx.SinglePeriodOptimization(
            objective, [cvx.LongOnly(), cvx.LeverageLimit(1)])

        result_svd = sim.backtest(policy, start_time='2020-01-01',
            end_time='2023-09-01')

        objective = cvx.ReturnsForecast() - 5 * cvx.FactorModelCovariance(
            num_factors=2)
        policy = cvx.SinglePeriodOptimization(
            objective, [cvx.LongOnly(), cvx.LeverageLimit(1)])

        result_eig = sim.backtest(policy, start_time='2020-01-01',
            end_time='2023-09-01')

        self.assertTrue(result_svd.sharpe_ratio > result_eig.sharpe_ratio)

        print(result_svd)
        print(result_eig)

    def test_bankruptcy(self):
        """Test policy bankruptcy"""
        sim = cvx.StockMarketSimulator(
            ['SPY', 'QQQ'],
            base_location=self.datadir)

        policy = cvx.SinglePeriodOptimization(
            cvx.ReturnsForecast(), [cvx.LeverageLimit(20)])
        with self.assertLogs(level='WARNING') as _:
            result = sim.backtest(policy,
                start_time='2020-02-15', end_time='2020-04-15')
        # print(result)
        print(result.h)
        self.assertTrue(result.h.shape[0] < 20)
        self.assertTrue(result.final_value < 0)

    def test_cache_missing_signature(self):
        """Test backtest with missing market data signature."""
        md = cvx.UserProvidedMarketData(
            returns=self.returns, volumes=self.volumes,
            cash_key='cash', base_location=self.datadir,
            min_history=pd.Timedelta('0d'))
        md.partial_universe_signature = lambda x: None

        simulator = cvx.MarketSimulator(market_data=md)

        # print(os.listdir(self.datadir/'cache'))

        policy = cvx.SinglePeriodOptimization(
            cvx.ReturnsForecast() - .5 * cvx.FullCovariance(),
            [cvx.LongOnly(applies_to_cash=True)])

        simulator.backtest(
            policy, start_time = self.returns.index[10],
            end_time = self.returns.index[20],
            )

if __name__ == '__main__':
    unittest.main()
