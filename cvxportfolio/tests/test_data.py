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
"""Unit tests for the data interfaces."""

import sys
import unittest
from copy import deepcopy

import numpy as np
import pandas as pd

from cvxportfolio.data import (DownloadedMarketData, Fred,
                               UserProvidedMarketData, YahooFinance,
                               _loader_csv, _loader_pickle, _loader_sqlite,
                               _storer_csv, _storer_pickle, _storer_sqlite)
from cvxportfolio.errors import DataError
from cvxportfolio.tests import CvxportfolioTest


class TestData(CvxportfolioTest):
    """Test SymbolData methods and interface."""

    def test_yfinance_download(self):
        """Test YfinanceBase."""

        data = YahooFinance._download("AAPL", start="2023-04-01",
                                       end="2023-04-15")
        # print(data)
        # print(data.loc["2023-04-10 13:30:00+00:00"]["Return"])
        # print(data.loc["2023-04-11 13:30:00+00:00", "Open"] /
        #       data.loc["2023-04-10 13:30:00+00:00", "Open"] - 1)
        self.assertTrue(np.isclose(
            data.loc["2023-04-10 13:30:00+00:00", "return"],
            data.loc["2023-04-11 13:30:00+00:00", "open"] /
            data.loc["2023-04-10 13:30:00+00:00", "open"] - 1,
        ))
        self.assertTrue(np.isnan(data.iloc[-1]["close"]))

    def test_fred(self):
        """Test basic Fred usage."""

        store = Fred(
            symbol="DFF", storage_backend='pickle',
            base_location=self.datadir)

        print(store.data)
        data = store.data
        self.assertTrue(np.isclose(data["2023-04-10"], 4.83))
        self.assertTrue(data.index[0] ==
            pd.Timestamp("1954-07-01 00:00:00+00:00"))

        # test update
        olddata = pd.Series(data.iloc[:-123], copy=True)
        olddata.index = olddata.index.tz_localize(None)
        newdata = store._preload(store._download("DFF", olddata))
        self.assertTrue(np.all(store.data == newdata))

    def test_yahoo_finance(self):
        """Test yahoo finance ability to store and retrieve."""

        store = YahooFinance(
            symbol="ZM", storage_backend='pickle',
            base_location=self.datadir)

        data = store.data

        # print(data)

        self.assertTrue(np.isclose(
            data.loc["2023-04-05 13:30:00+00:00", "return"],
            data.loc["2023-04-06 13:30:00+00:00", "open"] /
            data.loc["2023-04-05 13:30:00+00:00", "open"] - 1,
        ))

        store.update(grace_period=pd.Timedelta('1d'))
        data1 = store.load()
        # print(data1)

        self.assertTrue(np.isnan(data1.iloc[-1]["close"]))

        # print((data1.iloc[: len(data) - 1].Return -
        #       data.iloc[:-1].Return).describe().T)

        self.assertTrue(np.allclose(
            data1.loc[data.index[:-1]]['return'], data.iloc[:-1]['return']))

    def test_yahoo_finance_removefirstline(self):
        """Test that the first line of OHLCV is removed if there are NaNs."""

        # this symbol was found to have NaNs in the first line
        store = YahooFinance(
            symbol="CVX", storage_backend='pickle',
            base_location=self.datadir)

    @unittest.skipIf(sys.version_info.major == 3 and sys.version_info.minor < 11,
        "Issues with timezoned timestamps.")
    def test_sqlite3_store_series(self):
        """Test storing and retrieving of a Series with datetime index."""
        self.base_test_series(_loader_sqlite, _storer_sqlite)

    @unittest.skipIf(sys.version_info.major == 3 and sys.version_info.minor < 11,
        "Issues with timezoned timestamps.")
    def test_local_store_series(self):
        """Test storing and retrieving of a Series with datetime index."""
        self.base_test_series(_loader_csv, _storer_csv)

    def test_pickle_store_series(self):
        """Test storing and retrieving of a Series with datetime index."""
        self.base_test_series(_loader_pickle, _storer_pickle)

    def test_sqlite3_store_dataframe(self):
        """Test storing and retrieving of a DataFrame with datetime index."""
        self.base_test_dataframe(_loader_sqlite, _storer_sqlite)

    def test_local_store_dataframe(self):
        """Test storing and retrieving of a DataFrame with datetime index."""
        self.base_test_dataframe(_loader_csv, _storer_csv)

    def test_pickle_store_dataframe(self):
        """Test storing and retrieving of a DataFrame with datetime index."""
        self.base_test_dataframe(_loader_pickle, _storer_pickle)

    def test_local_store_multiindex(self):
        """Test storing and retrieving of a DataFrame with datetime index."""
        self.base_test_multiindex(_loader_csv, _storer_csv)

    def test_sqlite3_store_multiindex(self):
        """Test storing and retrieving of a DataFrame with datetime index."""
        self.base_test_multiindex(_loader_sqlite, _storer_sqlite)

    def test_pickle_store_multiindex(self):
        """Test storing and retrieving of a DataFrame with datetime index."""
        self.base_test_multiindex(_loader_pickle, _storer_pickle)

    def base_test_series(self, loader, storer):
        """Test storing and retrieving of a Series with datetime index."""

        for data in [
            pd.Series(
                0.0, pd.date_range("2020-01-01", "2020-01-10", tz='UTC-05:00'),
                name="test1"),
            pd.Series(
                3, pd.date_range("2020-01-01", "2020-01-10", tz='UTC'),
                name="test2"),
            pd.Series("hello",
                pd.date_range("2020-01-01", "2020-01-02",  tz='UTC-05:00',
                    freq="H"),
                name="test3"),
            # test overwrite
            pd.Series("hello",
                pd.date_range("2020-01-01", "2020-01-02",  tz='UTC', freq="H"),
                name="test3"),
            # test datetime conversion
            pd.Series(
                pd.date_range("2022-01-01", "2022-01-02",  tz='UTC',
                    freq="H"),
                pd.date_range("2020-01-01", "2020-01-02",  tz='UTC', freq="H"),
                name="test4"),
            ]:

            # print(data)
            # print(data.index)
            # print(data.index[0])
            # print(data.index[0].tzinfo)
            # print(data.index.dtype)
            # print(data.dtypes)

            storer(data.name, data, self.datadir)

            data1 = loader(data.name, self.datadir)
            # print(data1)
            # print(data1.index)
            # print(data1.index[0])
            # print(data1.index[0].tzinfo)
            # print(data1.index.dtype)
            # print(data1.dtypes)

            self.assertTrue(data.name == data1.name)
            self.assertTrue(all(data == data1))
            self.assertTrue(all(data.index == data1.index))
            self.assertTrue(data.dtypes == data1.dtypes)

        # test load not existent
        try:
            self.assertTrue(loader('blahblah', self.datadir) is None)
        except FileNotFoundError:
            pass

    def base_test_dataframe(self, loader, storer):
        """Test storing and retrieving of a DataFrame with datetime index."""

        index = pd.date_range("2020-01-01", "2020-01-02", freq="H", tz='UTC')
        data = {
            "one": range(len(index)),
            "two": np.arange(len(index)) / 19.0,
            "three": ["hello"] * len(index),
            "four": [np.nan] * len(index),
        }

        data["two"][2] = np.nan
        data = pd.DataFrame(data, index=index)
        # print(data)
        # print(data.index.dtype)
        # print(data.dtypes)

        storer("example", data, self.datadir)
        data1 = loader("example", self.datadir)
        # print(data1)
        # print(data1.index.dtype)
        # print(data1.dtypes)

        self.assertTrue(all(data == data1))
        self.assertTrue(all(data.index == data1.index))
        self.assertTrue(all(data.dtypes == data1.dtypes))

    def base_test_multiindex(self, loader, storer):
        """Test storing and retrieving of a Series or DataFrame with multi-.

        index.
        """
        # second level is object
        timeindex = pd.date_range("2022-01-01", "2022-01-30", tz='UTC')
        second_level = ["hello", "ciao", "hola"]
        index = pd.MultiIndex.from_product([timeindex, second_level])
        data = pd.DataFrame(np.random.randn(len(index), 3), index=index)
        data.columns = ["one", "two", "tre"]

        # print(data.index)
        # print(data)
        # print(data.index.dtype)
        # print(data.dtypes)

        storer("example", data, self.datadir)
        data1 = loader("example", self.datadir)

        # print(data1.index)
        # print(data1)
        # print(data1.index.dtype)
        # print(data1.dtypes)

        self.assertTrue(all(data == data1))
        self.assertTrue(all(data.index == data1.index))
        self.assertTrue(all(data.index.dtypes == data1.index.dtypes))
        self.assertTrue(all(data.dtypes == data1.dtypes))

        # second level is timestamp
        timeindex = pd.date_range("2022-01-01", "2022-01-30", tz='UTC')
        second_level = pd.date_range("2022-01-01", "2022-01-03", tz='UTC')
        index = pd.MultiIndex.from_product([timeindex, second_level])
        data = pd.DataFrame(np.random.randn(len(index), 3), index=index)
        data.columns = ["a", "b", "c"]

        #print(data.index)
        # print(data)
        # print(data.index.dtypes)
        # print(data.dtypes)

        storer("example", data, self.datadir)
        data1 = loader("example", self.datadir)

        #print(data1.index)
        # print(data1)
        # print(data1.index.dtypes)
        # print(data1.dtypes)

        self.assertTrue(all(data == data1))
        self.assertTrue(all(data.index == data1.index))
        self.assertTrue(all(data.index.dtypes == data1.index.dtypes))
        self.assertTrue(all(data.dtypes == data1.dtypes))


class TestMarketData(CvxportfolioTest):
    """Test MarketData methods and interface."""

    @staticmethod
    def strip_tz_and_hour(market_data):
        market_data.returns.index = \
            market_data.returns.index.tz_localize(None).floor("D")
        market_data.volumes.index = \
            market_data.volumes.index.tz_localize(None).floor("D")
        market_data.prices.index = \
            market_data.prices.index.tz_localize(None).floor("D")

    def test_market_data__downsample(self):
        """Test downsampling of market data."""
        md = DownloadedMarketData(['AAPL', 'GOOG'], base_location=self.datadir)

        # TODO: better to rewrite this test
        self.strip_tz_and_hour(md)

        idx = md.returns.index

        # not doing annual because XXXX-01-01 is holiday
        freqs = ['weekly', 'monthly', 'quarterly']
        testdays = ['2023-05-01', '2023-05-01', '2022-04-01']
        periods = [['2023-05-01', '2023-05-02', '2023-05-03', '2023-05-04',
                    '2023-05-05'],
                   idx[(idx >= '2023-05-01') & (idx < '2023-06-01')],
                   idx[(idx >= '2022-04-01') & (idx < '2022-07-01')]]

        for i in range(len(freqs)):

            new_md = deepcopy(md)

            new_md._downsample(freqs[i])
            print(new_md.returns)
            self.assertTrue(np.isnan(new_md.returns.GOOG.iloc[0]))
            self.assertTrue(np.isnan(new_md.volumes.GOOG.iloc[0]))
            self.assertTrue(np.isnan(new_md.prices.GOOG.iloc[0]))

            if freqs[i] == 'weekly':
                print((new_md.returns.index.weekday < 2).mean())
                self.assertTrue(
                    (new_md.returns.index.weekday < 2).mean() > .95)

            if freqs[i] == 'monthly':
                print((new_md.returns.index.day < 5).mean())
                self.assertTrue((new_md.returns.index.day < 5).mean() > .95)

            self.assertTrue(
                all(md.prices.loc[testdays[i]] ==
                    new_md.prices.loc[testdays[i]]))
            self.assertTrue(np.allclose(
                md.volumes.loc[periods[i]].sum(),
                new_md.volumes.loc[testdays[i]]))
            self.assertTrue(np.allclose(
                (1 + md.returns.loc[periods[i]]).prod(),
                1 + new_md.returns.loc[testdays[i]]))

    def test_market_data_methods(self):
        """Test objects returned by serve method of MarketDataInMemory."""
        t = self.returns.index[10]
        past_returns, current_returns, past_volumes, current_volumes, \
            current_prices = self.market_data.serve(t)
        self.assertTrue(current_returns.name == t)
        self.assertTrue(current_volumes.name == t)
        self.assertTrue(current_prices.name == t)
        self.assertTrue(np.all(past_returns.index < t))
        self.assertTrue(np.all(past_volumes.index < t))

    def test_market_data_object_safety(self):
        """Test safety of internal objects of MarketDataInMemory."""
        t = self.returns.index[10]

        past_returns, current_returns, past_volumes, current_volumes, \
            current_prices = self.market_data.serve(t)

        # with warnings.catch_warnings():
        #     warnings.simplefilter("ignore")
        with self.assertRaises(ValueError):
            past_returns.iloc[-2, -2] = 2.
        with self.assertRaises(ValueError):
            current_returns.iloc[-3] = 2.
        with self.assertRaises(ValueError):
            past_volumes.iloc[-1, -1] = 2.
        with self.assertRaises(ValueError):
            current_volumes.iloc[-3] = 2.
        with self.assertRaises(ValueError):
            current_prices.iloc[-3] = 2.

        obj2 = deepcopy(self.market_data)
        obj2._set_read_only()

        past_returns, _, past_volumes, _, current_prices = obj2.serve(t)

        with self.assertRaises(ValueError):
            current_prices.iloc[-1] = 2.

        current_prices.loc['BABA'] = 3.

        past_returns, _, past_volumes, _, current_prices = obj2.serve(t)

        self.assertFalse('BABA' in current_prices.index)

    def test_user_provided_market_data(self):
        """Test UserProvidedMarketData."""

        used_returns = self.returns.iloc[:, :-1]
        used_returns.index = used_returns.index.tz_localize('UTC')
        used_volumes = pd.DataFrame(self.volumes, copy=True)
        t = used_returns.index[20]
        used_volumes.index = used_volumes.index.tz_localize('UTC')
        used_prices = pd.DataFrame(self.prices, copy=True)
        used_prices.index = used_prices.index.tz_localize('UTC')

        with_download_fred = UserProvidedMarketData(
            returns=used_returns, volumes=used_volumes, prices=used_prices,
            cash_key='USDOLLAR', base_location=self.datadir)

        without_prices = UserProvidedMarketData(
            returns=used_returns, volumes=used_prices, cash_key='USDOLLAR',
            base_location=self.datadir)
        past_returns, _, past_volumes, _,  current_prices = \
            without_prices.serve(t)
        self.assertTrue(current_prices is None)

        without_volumes = UserProvidedMarketData(
            returns=used_returns, cash_key='USDOLLAR',
            base_location=self.datadir)
        past_returns, current_returns, past_volumes, current_volumes, \
            current_prices = without_volumes.serve(t)

        self.assertTrue(past_volumes is None)
        self.assertTrue(current_volumes is None)

        with self.assertRaises(SyntaxError):
            UserProvidedMarketData(returns=self.returns, volumes=self.volumes,
                       prices=self.prices.iloc[:, :-1], cash_key='cash')

        with self.assertRaises(SyntaxError):
            UserProvidedMarketData(
                returns=self.returns,
                volumes=self.volumes.iloc[:, :-3],
                prices=self.prices, cash_key='cash')

        with self.assertRaises(SyntaxError):
            used_prices = pd.DataFrame(
                self.prices, index=self.prices.index,
                columns=self.prices.columns[::-1])
            UserProvidedMarketData(returns=self.returns, volumes=self.volumes,
                       prices=used_prices, cash_key='cash')

        with self.assertRaises(SyntaxError):
            used_volumes = pd.DataFrame(
                self.volumes, index=self.volumes.index,
                columns=self.volumes.columns[::-1])
            UserProvidedMarketData(returns=self.returns, volumes=used_volumes,
                       prices=self.prices, cash_key='cash')

    def test_market_data_full(self):
        """Test serve method of DownloadedMarketData."""

        md = DownloadedMarketData(['AAPL', 'ZM'], base_location=self.datadir)
        assert np.all(md.full_universe == ['AAPL', 'ZM', 'USDOLLAR'])

        t = md.returns.index[-40]

        past_returns, _, past_volumes, _, current_prices = md.serve(t)
        self.assertFalse(past_volumes is None)
        self.assertFalse(current_prices is None)

    def test_signature(self):
        """Test partial-universe signature of MarketData."""

        md = DownloadedMarketData(['AAPL', 'ZM'], base_location=self.datadir)

        sig1 = md.partial_universe_signature(md.full_universe)

        md = DownloadedMarketData(['AAPL', 'ZM'], trading_frequency='monthly',
            base_location=self.datadir)

        sig2 = md.partial_universe_signature(md.full_universe)

        self.assertFalse(sig1 == sig2)

        md = DownloadedMarketData(['AAPL', 'ZM', 'GOOG'],
            trading_frequency='monthly',
            base_location=self.datadir)

        sig3 = md.partial_universe_signature(
            pd.Index(['AAPL', 'ZM', 'USDOLLAR']))

        self.assertTrue(sig3 == sig2)

        md = DownloadedMarketData(['WM2NS'],
            datasource='Fred',
            base_location=self.datadir)

        print(md.partial_universe_signature(md.full_universe))

    def test_download_errors(self):
        """Test single-symbol download error."""

        class YahooFinanceErroneous(YahooFinance):

            def _download(self, symbol, current, grace_period):
                res = super()._download(symbol, current,
                    grace_period=grace_period)
                res.iloc[-1, 0 ] = np.nan
                return res

        a = YahooFinanceErroneous('AMZN', base_location=self.datadir)
        with self.assertLogs(level='ERROR') as _:
            a = YahooFinanceErroneous(
                'AMZN', base_location=self.datadir)

        class YahooFinanceErroneous2(YahooFinance):

            def _download(self, symbol, current, grace_period):
                res = super()._download(symbol, current,
                    grace_period=grace_period)
                res.iloc[-20] = np.nan
                return res
        with self.assertLogs(level='WARNING') as _:
            a = YahooFinanceErroneous2('GOOGL',
                base_location=self.datadir)
        with self.assertLogs(level='WARNING') as _:
            a = YahooFinanceErroneous2(
                'GOOGL', base_location=self.datadir)

        class FredErroneous(Fred):

            def _download(self, symbol, current, grace_period):
                res = super()._download(symbol, current,
                    grace_period=grace_period)
                res.iloc[-1] = np.nan
                return res

        a = FredErroneous('DFF', base_location=self.datadir)
        with self.assertLogs(level='ERROR') as _:
            a = FredErroneous(
                'DFF', base_location=self.datadir)

    def test_yahoo_finance_errors(self):
        """Test errors with Yahoo Finance."""

        import logging
        import sys
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

        with self.assertRaises(DataError):
            YahooFinance("DOESNTEXIST", base_location=self.datadir)

    def test_yahoo_finance_cleaning(self):
        """Test our logic to clean Yahoo Finance data."""

        data = YahooFinance("ENI.MI", base_location=self.datadir).data
        self.assertTrue((data.valuevolume == 0).sum() > 0)
        self.assertTrue(data.iloc[:-1].isnull().sum().sum() == 0)


if __name__ == '__main__':
    unittest.main()
