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
"""We make the tests a sub-package so we can ship them."""

import shutil
import tempfile
import unittest
from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd

import cvxportfolio as cvx


class CvxportfolioTest(unittest.TestCase):
    """Base class for Cvxportfolio unit tests."""

    @classmethod
    def setUpClass(cls):
        """Initialize test class."""
        cls.datadir = Path(tempfile.mkdtemp())
        print('created', cls.datadir)

        cls.sigma = pd.read_csv(
            Path(__file__).parent / "sigmas.csv",
            index_col=0, parse_dates=[0])
        cls.returns = pd.read_csv(
            Path(__file__).parent /
            "returns.csv", index_col=0, parse_dates=[0])
        cls.volumes = pd.read_csv(
            Path(__file__).parent /
            "volumes.csv", index_col=0, parse_dates=[0])
        cls.prices = pd.DataFrame(
            np.random.uniform(10, 200, size=cls.volumes.shape),
            index=cls.volumes.index, columns=cls.volumes.columns)
        cls.market_data = cvx.UserProvidedMarketData(
            returns=cls.returns, volumes=cls.volumes, prices=cls.prices,
            cash_key='cash',
            min_history=pd.Timedelta('0d'))
        cls.universe = cls.returns.columns
        cls.w_plus = cp.Variable(cls.returns.shape[1])
        cls.w_plus_minus_w_bm = cp.Variable(cls.returns.shape[1])
        cls.z = cp.Variable(cls.returns.shape[1])
        cls.N = cls.returns.shape[1]

    @classmethod
    def tearDownClass(cls):
        """Finalize test class."""
        print('removing', cls.datadir)
        shutil.rmtree(cls.datadir)
