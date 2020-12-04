import numpy as np
import argparse, json, math
import os, glob

import flow, utils, source

import torch, torchvision
from torch import nn

from encoder import rans, coder
from utils import cdfDiscreteLogitstic, cdfMixDiscreteLogistic


parser = argparse.ArgumentParser(description="")

parser.add_argument("-folder", default=None, help="Path to load the trained model")
parser.add_argument("-cuda", type=int, default=-1, help="Which device to use with -1 standing for CPU, number bigger than -1 is N.O. of GPU.")
parser.add_argument("-nbins", type=int, default=4096, help="bin number of ran")
parser.add_argument("-batch", type=int, default=-1, help="batch size")
parser.add_argument("-precision", type=int, default=24, help="precision of CDF")
parser.add_argument("-earlyStop", type=int, default=10, help="fewer batch of testing")
parser.add_argument("-best", action='store_false', help="if load the best model")


args = parser.parse_args()

device = torch.device("cpu" if args.cuda < 0 else "cuda:" + str(args.cuda))

if args.folder is None:
    raise Exception("No loading")
else:
    rootFolder = args.folder
    if rootFolder[-1] != '/':
        rootFolder += '/'
    with open(rootFolder + "parameter.json", 'r') as f:
        config = json.load(f)
        locals().update(config)

        target = config['target']
        repeat = config['repeat']
        nhidden = config['nhidden']
        hchnl = config['hchnl']
        nMixing = config['nMixing']
        batch = config['batch']

if args.batch != -1:
    batch = args.batch
# Building the target dataset
if target == "CIFAR":
    # Define dimensions
    targetSize = [3, 32, 32]
    dimensional = 2
    channel = targetSize[0]
    blockLength = targetSize[-1]

    # Define nomaliziation and decimal
    decimal = flow.ScalingNshifting(256, -128)
    rounding = utils.roundingWidentityGradient

    # Building train & test datasets
    lambd = lambda x: (x * 255).byte().to(torch.float32).to(device)
    trainsetTransform = torchvision.transforms.Compose([torchvision.transforms.ToTensor(), torchvision.transforms.Lambda(lambd)])
    trainTarget = torchvision.datasets.CIFAR10(root='./data/cifar', train=True, download=True, transform=trainsetTransform)
    testTarget = torchvision.datasets.CIFAR10(root='./data/cifar', train=False, download=True, transform=trainsetTransform)
    targetTrainLoader = torch.utils.data.DataLoader(trainTarget, batch_size=batch, shuffle=False)
    targetTestLoader = torch.utils.data.DataLoader(testTarget, batch_size=batch, shuffle=False)
elif target == "ImageNet32":
    # Define dimensions
    targetSize = [3, 32, 32]
    dimensional = 2
    channel = targetSize[0]
    blockLength = targetSize[-1]

    # Define nomaliziation and decimal
    decimal = flow.ScalingNshifting(256, -128)
    rounding = utils.roundingWidentityGradient

    # Building train & test datasets
    lambd = lambda x: (x * 255).byte().to(torch.float32).to(device)
    trainsetTransform = torchvision.transforms.Compose([torchvision.transforms.ToTensor(), torchvision.transforms.Lambda(lambd)])
    trainTarget = utils.ImageNet(root='./data/ImageNet32', train=True, download=True, transform=trainsetTransform)
    testTarget = utils.ImageNet(root='./data/ImageNet32', train=False, download=True, transform=trainsetTransform)
    targetTrainLoader = torch.utils.data.DataLoader(trainTarget, batch_size=batch, shuffle=False)
    targetTestLoader = torch.utils.data.DataLoader(testTarget, batch_size=batch, shuffle=False)

elif target == "ImageNet64":
    # Define dimensions
    targetSize = [3, 64, 64]
    dimensional = 2
    channel = targetSize[0]
    blockLength = targetSize[-1]

    # Define nomaliziation and decimal
    decimal = flow.ScalingNshifting(256, -128)
    rounding = utils.roundingWidentityGradient

    # Building train & test datasets
    lambd = lambda x: (x * 255).byte().to(torch.float32).to(device)
    trainsetTransform = torchvision.transforms.Compose([torchvision.transforms.ToTensor(), torchvision.transforms.Lambda(lambd)])
    trainTarget = utils.ImageNet(root='./data/ImageNet64', train=True, download=True, transform=trainsetTransform, d64=True)
    testTarget = utils.ImageNet(root='./data/ImageNet64', train=False, download=True, transform=trainsetTransform, d64=True)
    targetTrainLoader = torch.utils.data.DataLoader(trainTarget, batch_size=batch, shuffle=False)
    targetTestLoader = torch.utils.data.DataLoader(testTarget, batch_size=batch, shuffle=False)

elif target == "MNIST":
    pass
else:
    raise Exception("No such target")

if args.best:
    name = max(glob.iglob(os.path.join(rootFolder, '*.saving')), key=os.path.getctime)
else:
    name = max(glob.iglob(os.path.join(rootFolder, 'savings', '*.saving')), key=os.path.getctime)

# load the model
print("load saving at " + name)
f = torch.load(name, map_location=device)

tmpLine = targetSize[-1] ** 2 // 4
shapeList = []
while tmpLine != 1:
    shapeList.append([3, tmpLine, 3])
    tmpLine = tmpLine // 4

shapeList.append([3, 1, 4])


def im2grp(t):
    return t.reshape(t.shape[0], t.shape[1], t.shape[2] // 2, 2, t.shape[3] // 2, 2).permute([0, 1, 2, 4, 3, 5]).reshape(t.shape[0], t.shape[1], -1, 4)


def grp2im(t):
    return t.reshape(t.shape[0], t.shape[1], int(t.shape[2] ** 0.5), int(t.shape[2] ** 0.5), 2, 2).permute([0, 1, 2, 4, 3, 5]).reshape(t.shape[0], t.shape[1], int(t.shape[2] ** 0.5) * 2, int(t.shape[2] ** 0.5) * 2)


def divide(z):
    parts = []
    ul = z
    for no in range(int(math.log(blockLength, 2))):
        if no == int(math.log(blockLength, 2)) - 1:
            z_ = ul.reshape(*ul.shape[:2], 1, 4) - (decimal.forward_(f.prior.lastPrior.mean.permute([1, 2, 3, 0])) * torch.softmax(f.prior.lastPrior.mixing, -1)).sum(-1).reshape(1, *f.prior.lastPrior.mean.shape[1:]).int() + args.nbins // 2
        else:
            _x = im2grp(ul)
            z_ = _x[:, :, :, 1:].contiguous() - decimal.forward_(f.meanList[no]).int() + args.nbins // 2
            ul = _x[:, :, :, 0].reshape(*_x.shape[:2], int(_x.shape[2] ** 0.5), int(_x.shape[2] ** 0.5)).contiguous()
        parts.append(z_.reshape(z_.shape[0], -1).int().detach())
    return torch.cat(parts, -1).numpy()


def join(rcnZ):
    zparts = []
    for no in range(int(math.log(blockLength, 2))):
        rcnZpart = rcnZ[:, :np.prod(shapeList[no])].reshape(rcnZ.shape[0], *shapeList[no])
        rcnZ = rcnZ[:, np.prod(shapeList[no]):]

        if no == int(math.log(blockLength, 2)) - 1:
            rcnZpart = rcnZpart + (decimal.forward_(f.prior.lastPrior.mean.permute([1, 2, 3, 0])) * torch.softmax(f.prior.lastPrior.mixing, -1)).sum(-1).reshape(1, *f.prior.lastPrior.mean.shape[1:]).int() - args.nbins // 2
        else:
            rcnZpart = rcnZpart + decimal.forward_(f.meanList[no]).int() - args.nbins // 2
        zparts.append(rcnZpart)

    retZ = grp2im(zparts[-1]).contiguous()
    for term in reversed(zparts[:-1]):
        tmp = term.reshape(*retZ.shape, 3)
        retZ = retZ.reshape(*retZ.shape, 1)
        tmp = torch.cat([retZ, tmp], -1).reshape(*retZ.shape[:2], -1, 4)
        retZ = grp2im(tmp).contiguous()
    return retZ


def cdf2int(cdf):
    return (cdf * ((1 << args.precision) - args.nbins)).int().detach() + torch.arange(args.nbins).reshape(-1, 1, 1, 1, 1)


def calCDF():
    CDF = []
    _bins = torch.arange(-args.nbins // 2, args.nbins // 2).reshape(-1, 1, 1, 1, 1)
    for no, mean in enumerate(f.meanList):
        bins = _bins - 1 + decimal.forward_(mean).int()
        cdf = cdfDiscreteLogitstic(bins, mean, f.scaleList[no], decimal=f.decimal)
        CDF.append(cdf2int(cdf).reshape(args.nbins, batch, -1))

    bins = _bins - 1 + (decimal.forward_(f.prior.lastPrior.mean.permute([1, 2, 3, 0])) * f.prior.lastPrior.mixing).sum(-1).reshape(1, *f.prior.lastPrior.mean.shape[1:]).int()
    cdf = cdfMixDiscreteLogistic(bins, f.prior.lastPrior.mean, f.prior.lastPrior.logscale, f.prior.lastPrior.mixing, decimal=f.decimal).repeat(1, 200, 1, 1, 1)
    CDF.append(cdf2int(cdf).reshape(args.nbins, batch, -1))

    CDF = torch.cat(CDF, -1).numpy()
    return CDF


def testBPD(loader, earlyStop=-1):
    actualBPD = []
    theoryBPD = []
    ERR = []

    count = 0
    with torch.no_grad():
        for samples, _ in loader:
            count += 1
            z, _ = f.inverse(samples)

            zparts = divide(z)

            CDF = calCDF()

            state = []

            for i in range(batch):
                symbols = zparts[i]
                s = rans.x_init
                for j in reversed(range(symbols.shape[-1])):
                    cdf = CDF[:, i, j]
                    s = coder.encoder(cdf, symbols[j], s)
                state.append(rans.flatten(s))

            actualBPD.append(32 / (np.prod(samples.shape[1:])) * np.mean([s.shape[0] for s in state]))
            theoryBPD.append((-f.logProbability(samples).mean() / (np.prod(samples.shape[1:]) * np.log(2.))).detach().item())

            rcnParts = []
            for i in range(batch):
                s = rans.unflatten(state[i])
                symbols = []
                for j in range(np.prod(targetSize)):
                    cdf = CDF[:, i, j]
                    s, rcnSymbol = coder.decoder(cdf, s)
                    symbols.append(rcnSymbol)
                rcnParts.append(torch.tensor(symbols).reshape(1, -1))
            rcnParts = torch.cat(rcnParts, 0)

            rcnZ = join(rcnParts)

            rcnSamples, _ = f.forward(rcnZ.float())

            ERR.append(torch.abs(samples - rcnSamples).sum().item())

            if count >= earlyStop and earlyStop > 0:
                break

    actualBPD = np.array(actualBPD)
    theoryBPD = np.array(theoryBPD)
    ERR = np.array(ERR)

    print("===========================SUMMARY==================================")
    print("Actual Mean BPD:", actualBPD.mean(), "Theory Mean BPD:", theoryBPD.mean(), "Mean Error:", ERR.mean())

    return actualBPD, theoryBPD, ERR


print("Train Set:")
testBPD(targetTrainLoader, earlyStop=args.earlyStop)
print("Test Set:")
testBPD(targetTestLoader, earlyStop=args.earlyStop)