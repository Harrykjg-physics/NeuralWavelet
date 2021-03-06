from flowRelated import *

import os
import sys
sys.path.append(os.getcwd())

import torch, math
from torch import nn
import numpy as np
import utils
import flow
import source
import utils
from numpy.testing import assert_allclose

#torch.manual_seed(42)

def test_bijective():
    decimal = flow.ScalingNshifting(256, -128)

    layerList = []
    for i in range(4 * 2):
        f = torch.nn.Sequential(torch.nn.Conv2d(9, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 3, 3, padding=1))
        layerList.append(f)

    meanNNlist = []
    scaleNNlist = []
    meanNNlist.append(torch.nn.Sequential(torch.nn.Conv2d(3, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True)))
    scaleNNlist.append(torch.nn.Sequential(torch.nn.Conv2d(3, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True)))

    t = flow.SimpleMERA(8, layerList, meanNNlist, scaleNNlist, 2, None, 5, decimal, utils.roundingWidentityGradient)

    samples = torch.randint(0, 255, (100, 3, 8, 8)).float()

    zSamples, _ = t.inverse(samples)
    rcnSamples, _ = t.forward(zSamples)
    prob = t.logProbability(samples)

    assert_allclose(samples.detach().numpy(), rcnSamples.detach().numpy())

    # Test the depth argument
    t = flow.SimpleMERA(8, layerList, meanNNlist, scaleNNlist, 2, 2, 5, decimal, utils.roundingWidentityGradient)

    samples = torch.randint(0, 255, (100, 3, 8, 8)).float()

    zSamples, _ = t.inverse(samples)
    rcnSamples, _ = t.forward(zSamples)
    #prob = t.logProbability(samples)

    assert_allclose(samples.detach().numpy(), rcnSamples.detach().numpy())

def test_saveload():
    decimal = flow.ScalingNshifting(256, -128)

    layerList = []
    for i in range(4):
        f = torch.nn.Sequential(torch.nn.Conv2d(9, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 3, 3, padding=1))
        layerList.append(f)

    meanNNlist = []
    scaleNNlist = []
    meanNNlist.append(torch.nn.Sequential(torch.nn.Conv2d(3, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True)))
    scaleNNlist.append(torch.nn.Sequential(torch.nn.Conv2d(3, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True)))

    t = flow.SimpleMERA(8, layerList, meanNNlist, scaleNNlist, 1, None, 5, decimal, utils.roundingWidentityGradient)

    decimal = flow.ScalingNshifting(256, -128)

    layerList = []
    for i in range(4):
        f = torch.nn.Sequential(torch.nn.Conv2d(9, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 3, 3, padding=1))
        layerList.append(f)

    meanNNlist = []
    scaleNNlist = []
    meanNNlist.append(torch.nn.Sequential(torch.nn.Conv2d(3, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True)))
    scaleNNlist.append(torch.nn.Sequential(torch.nn.Conv2d(3, 9, 3, padding=1), torch.nn.ReLU(inplace=True), torch.nn.Conv2d(9, 9, 1, padding=0), torch.nn.ReLU(inplace=True)))

    tt = flow.SimpleMERA(8, layerList, meanNNlist, scaleNNlist, 1, None, 5, decimal, utils.roundingWidentityGradient)

    samples = torch.randint(0, 255, (100, 3, 8, 8)).float()

    torch.save(t.save(), "testsaving.saving")
    tt.load(torch.load("testsaving.saving"))

    tzSamples, _ = t.inverse(samples)
    ttzSamples, _ = tt.inverse(samples)

    rcnSamples, _ = t.forward(tzSamples)
    ttrcnSamples, _ = tt.forward(ttzSamples)

    assert_allclose(tzSamples.detach().numpy(), ttzSamples.detach().numpy())
    assert_allclose(samples.detach().numpy(), rcnSamples.detach().numpy())
    assert_allclose(rcnSamples.detach().numpy(), ttrcnSamples.detach().numpy())


if __name__ == "__main__":
    test_bijective()
    #test_saveload()