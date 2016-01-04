import re
from settings import Settings
from compiledREs import *

MAX_CFR_INDEX = 4
MIN_HARQ_DELAY = 4
MAX_HARQ_DELAY = 8
TDD_HARQ_DELAY = 4
PUSCH_MEAS_REPORT = 1
PUCCH_MEAS_REPORT = 2

WIDEBAND_CQI_BITMASK = 15
NUM_WIDEBAND_CQI_BITS = 4
PMI_4_TX_BITMASK = 15
PMI_2_TX_BITMASK = 3
MAX_NUM_HARQ_IDX = 10
MAX_NUM_CW = 2

HARQ_INDICATION_NACK = 0
HARQ_INDICATION_DTX = 4
HARQ_INDICATION_UNKNOWN = 5
HARQ_INDICATION_INVALID = 15

PRB_TO_NUM_SUBBAND_TABLE = {6: 1, 15: 4, 25: 7, 50: 9, 75: 10, 100: 13}
RV_TO_INDEX_TABLE = {2:0, 3:1, 1:2} # redundancy version to index table

# returns the localDu time as int in concatenated format
def getglobaltime(line):
    """

    :rtype: int - value is a concatenation of the month,day,hour,minute,second time
    """
    time = GLOBAL_TIME.match(line)
    sfInUm = GET_SF_MICRO_SEC.search(line)

    # check if we have a valid system time
    if (time):
        gTime = (int(time.group(1) + time.group(2) + time.group(3) + time.group(4) + time.group(5) +
                    time.group(6)) - int(sfInUm.group(1))*10) / 1000
    # if we do not have a valid system time assume it was aTest logs ie. global time is all xxx's [xxxx-xx-xx]
    # here, we do assume sfn never rolls over
    else:
        aTestTime = ATEST_TIME.search(line)
        gTime = int(aTestTime.group(1) + aTestTime.group(2))

    if Settings.global_starting_time == 0:
        Settings.global_starting_time = gTime

    return gTime - Settings.global_starting_time

# returns the subframe the log was printed in
def getsubframe(line):
    sf = GET_SF.search(line)

    if sf is None:
        print 'Error: could not find subframe in line: \n %d' % line
    return int(sf.group(1))


class UeData:
    def __init__(self):
        self.dataPerTti = []  # will contain a list of TtiData objects
        self.lastHarqProcTx = [None] * MAX_NUM_HARQ_IDX * MAX_NUM_CW  # contains TtiData object for last harq process
        # scheduled important so we know which object to update when we receive harq feedback
        self.lastSf = 0
        self.lastGlobalTime = 0
        self.summary = Summary()


    def __str__(self):
        string = ''
        for tti in self.dataPerTti:
            string += '%s \n' % tti

        return string

    def decode73(self, line, rFile):
        globalTime = getglobaltime(line)
        subFrame = getsubframe(line)
        if self.isnewtti(globalTime, subFrame):
            self.addnewtti(globalTime, subFrame)
        self.dataPerTti[-1].decode73(line, rFile)
        self.update_lastharqproc()

    def isnewtti(self, globalTime, subFrame):
        if abs(globalTime - self.lastGlobalTime) > 1 or subFrame != self.lastSf:
            return 1
        return 0

    def addnewtti(self, globalTime, subFrame):
        self.dataPerTti.append(TtiOccurrence())
        if self.dataPerTti.__len__() >= 2:
            self.dataPerTti[-1].cfrData = self.dataPerTti[-2].cfrData
        self.lastGlobalTime = globalTime
        self.lastSf = subFrame

    def update_lastharqproc(self):
        harqIdx = int(self.dataPerTti[-1].txData.harqIdx)

        if self.lastHarqProcTx[harqIdx] is not None and self.current_harqproc_valid(harqIdx):
            self.lastHarqProcTx[harqIdx + MAX_NUM_HARQ_IDX] = self.dataPerTti[-1]
        else:
            self.lastHarqProcTx[harqIdx] = self.dataPerTti[-1]

    def current_harqproc_valid(self, harqIdx):
        if self.dataPerTti[-1].txData.globalTime - self.lastHarqProcTx[harqIdx].txData.globalTime <= 4:
            return 1
        return 0

    '''
    :rtype: int isValid - 0 is invalid, 1 is valid
    '''

    def is_lastharqproc_valid(self, harqGlobalTime, dlHarqProcessId):
        isValid = 0
        if self.lastHarqProcTx[dlHarqProcessId] is not None:
            txData = self.lastHarqProcTx[dlHarqProcessId].txData
            # check that we are not overwriting data
            if txData.harqFdbk[0] == HARQ_INDICATION_UNKNOWN and txData.harqFdbk[1] == HARQ_INDICATION_UNKNOWN:
                timeDelta = abs(harqGlobalTime - txData.globalTime)
                if timeDelta <= (MAX_HARQ_DELAY + TDD_HARQ_DELAY * Settings.isTdd) and timeDelta >= MIN_HARQ_DELAY:
                    isValid = 1
            else:
                print "Error, we tried to overwrite harq data"
        return isValid

    '''
    typedef S16 ElibBbBaseCommonDetectedHarqIndicationE;
    #define ELIB_BBBASE_COMMON_DETECTED_HARQ_INDICATION_NACK_NACK    0
    #define ELIB_BBBASE_COMMON_DETECTED_HARQ_INDICATION_NACK_ACK     1
    #define ELIB_BBBASE_COMMON_DETECTED_HARQ_INDICATION_ACK_NACK     2
    #define ELIB_BBBASE_COMMON_DETECTED_HARQ_INDICATION_ACK_ACK      3
    #define ELIB_BBBASE_COMMON_DETECTED_HARQ_INDICATION_DTX          4
    #define ELIB_BBBASE_COMMON_DETECTED_HARQ_INDICATION_UNKNOWN      5
    #define ELIB_BBBASE_COMMON_DETECTED_HARQ_INDICATION_ANY          6
    #define ELIB_BBBASE_COMMON_DETECTED_HARQ_INDICATION_INVALID      15
    '''

    def set_harq_fdd(self, harqGlobalTime, dlHarqProcessId, harqInd, lineNo):
        if self.is_lastharqproc_valid(harqGlobalTime, dlHarqProcessId):
            self.set_harq_fdbk(dlHarqProcessId, harqInd, lineNo)
        else:
            print 'Warning: no reference back to scheduled data'

    # TODO: break up set_harq_tdd method into getValidHarqBundleSf, calc_num_bundled_tx etc as needed.


    def set_harq_tdd(self, harqGlobalTime, harqProcessId, harqInd, lineNo):
        harqBundledSFs1 = [9, 0, 1, 3]
        harqBundledSFs2 = [4, 5, 6, 8]

        if self.lastHarqProcTx[harqProcessId] is not None:
            currentHarqSf = self.lastHarqProcTx[harqProcessId].txData.txSf
        else:
            return

        if currentHarqSf in harqBundledSFs1:
            harqBundle = harqBundledSFs1
        elif currentHarqSf in harqBundledSFs2:
            harqBundle = harqBundledSFs2
        else:
            print "Error: current subframe did not match any configured Tdd bundles sf=%s" % currentHarqSf
            return

        harqIdxInBundle = []
        nBundledTx = 0
        for harqIdx in range(0, MAX_NUM_HARQ_IDX * MAX_NUM_CW):
            if self.lastHarqProcTx[harqIdx] is not None:
                if self.lastHarqProcTx[harqIdx].txData.txSf in harqBundle and \
                        self.is_lastharqproc_valid(harqGlobalTime, harqIdx):
                    harqIdxInBundle.append(harqIdx)
                    nBundledTx += 1
        for bundledHarqIdx in harqIdxInBundle:
            self.set_numbundledtx(nBundledTx, bundledHarqIdx)
            self.set_harq_fdbk(bundledHarqIdx, harqInd, lineNo)


    def set_harq_fdbk(self, dlHarqProcessId, harqInd, lineNo):
        txData = self.lastHarqProcTx[dlHarqProcessId].txData
        if harqInd <= 3:
            txData.harqFdbk[0] = (harqInd & 1) != 0
            txData.harqFdbk[1] = (harqInd & 2) != 0
        else:
            txData.harqFdbk[0] = harqInd
            if txData.nrCw == 2:
                txData.harqFdbk[1] = harqInd
        txData.harqFdbkLineNo = lineNo

        if Settings.isTdd:
            self.lastHarqProcTx[dlHarqProcessId] = None
        else:
            self.lastHarqProcTx[dlHarqProcessId] = self.lastHarqProcTx[dlHarqProcessId + MAX_NUM_HARQ_IDX]
            self.lastHarqProcTx[dlHarqProcessId + MAX_NUM_HARQ_IDX] = None


    def set_numbundledtx(self, nBundledTx, bundledHarqIdx):
        self.lastHarqProcTx[bundledHarqIdx].txData.nBundled = nBundledTx

    def add_cfr_data(self, cfrData):
        self.dataPerTti[-1].cfrData = cfrData

    def update_bler(self):
        if Settings.isHarqFeedback:
            for index in range(0, len(self.dataPerTti)):
                txData = self.dataPerTti[index].txData
                newPm = self.dataPerTti[index].pms

                cw1Index = 0
                cw2Index = 1

                if index > 0:
                    prevPm = self.dataPerTti[index-1].pms
                else:
                    prevPm = Pms()

                if txData.harqFdbk[0] <= 1 and txData.mcs[0] <= 28:
                    newPm.calc_bler(prevPm.bler[cw1Index], txData.harqFdbk[cw1Index], cw1Index, txData.nBundled)
                else:
                    newPm.bler[cw1Index] = prevPm.bler[cw1Index]

                if txData.nrCw >= 2 and txData.harqFdbk[cw2Index] <= 1 and txData.mcs[cw2Index] <= 28:
                    newPm.calc_bler(prevPm.bler[cw2Index], txData.harqFdbk[cw2Index], cw2Index,
                                    txData.nBundled)
                else:
                    newPm.bler[cw2Index] = prevPm.bler[cw2Index]

    def update_throughput(self):
        if Settings.isHarqFeedback:
            for index in range(0, len(self.dataPerTti)):
                txData = self.dataPerTti[index].txData
                newPm = self.dataPerTti[index].pms

                cw1Index = 0
                cw2Index = 1

                if index > 0:
                    prevPm = self.dataPerTti[index-1].pms
                else:
                    prevPm = Pms()

                if txData.harqFdbk[cw1Index] <= 1:
                    newPm.calc_throughput(prevPm, txData.tbs[cw1Index], txData.harqFdbk[cw1Index], cw1Index)
                else:
                    newPm.avgThroughput[cw1Index] = prevPm.avgThroughput[cw1Index]
                    newPm.peakThroughput[cw1Index] = prevPm.peakThroughput[cw1Index]
                    newPm.throughputWindow = prevPm.throughputWindow[:]
                if txData.nrCw >= 2 and txData.harqFdbk[cw2Index] <= 1:
                    newPm.calc_throughput(prevPm, txData.tbs[cw2Index], txData.harqFdbk[cw2Index], cw2Index)
                else:
                    newPm.avgThroughput[cw2Index] = prevPm.avgThroughput[cw2Index]
                    newPm.peakThroughput[cw2Index] = prevPm.peakThroughput[cw2Index]

    def update_uesummary(self):
        if self.dataPerTti[-1].txData.globalTime > self.dataPerTti[0].txData.globalTime:
            self.summary.schedulingFreq = 100.0 * self.dataPerTti.__len__() / \
                                  (self.dataPerTti[-1].txData.globalTime - self.dataPerTti[0].txData.globalTime)

        mcsSum = [0.0, 0.0]
        tbSizeSum = [0, 0]
        totalTx = [0, 0]
        for index in range(0, len(self.dataPerTti)):
            self.count_tx_type(index, 0)
            ttiTxData = self.dataPerTti[index].txData
            for cwIndex in range(0, ttiTxData.nrCw):
                if ttiTxData.mcs[cwIndex] <= 28:
                    mcsSum[cwIndex] += ttiTxData.mcs[cwIndex]
                    tbSizeSum[cwIndex] += ttiTxData.tbs[cwIndex]
                    totalTx[cwIndex] += 1
                if ttiTxData.redundancyVer[cwIndex] > 0:
                    if ttiTxData.harqFdbk[cwIndex] == 1:
                        self.summary.reTxAttemptCount[cwIndex][RV_TO_INDEX_TABLE[ttiTxData.redundancyVer[0]]] += 1
                    elif ttiTxData.redundancyVer[cwIndex] == 1:
                        self.summary.reTxAttemptCount[cwIndex][3] += 1
                

        print mcsSum[1], self.summary.numAck[1], str(len(self.dataPerTti))

        if totalTx[0] > 0:
            self.summary.avgMcs[0] = mcsSum[0]/totalTx[0]
            self.summary.avgTbSize[0] = tbSizeSum[0]/totalTx[0]
        if totalTx[1] > 0:
            self.summary.avgMcs[1] = mcsSum[1]/totalTx[1]
            self.summary.avgTbSize[1] = tbSizeSum[1]/totalTx[1]

    def count_tx_type(self, ttiIndex, cwIndex):

        # if tbs > 0 we have a valid transmission
        if self.dataPerTti[ttiIndex].txData.tbs[cwIndex] > 0:
            currentHarqFdbk = self.dataPerTti[ttiIndex].txData.harqFdbk[cwIndex]
            self.summary.numTx[cwIndex] += 1
            # 5 is unknown feedback
            if currentHarqFdbk == 5:
                self.summary.numUnknown[cwIndex] += 1
            # 4 is Dtx feedback
            elif currentHarqFdbk == HARQ_INDICATION_DTX:
                self.summary.numDtx[cwIndex] += 1
            elif currentHarqFdbk == HARQ_INDICATION_NACK:
                self.summary.numNack[cwIndex] += 1
            elif currentHarqFdbk == HARQ_INDICATION_INVALID:
                self.summary.numInvalid[cwIndex] += 1
            else:
                self.summary.numAck[cwIndex] += 1
        if cwIndex == 0 and self.dataPerTti[ttiIndex].txData.nrCw == 2:
            self.count_tx_type(ttiIndex, cwIndex + 1)


# creating TtiData for potential addition of more classes to TtiData, allowing us to offload txData class


class TtiOccurrence:
    def __init__(self):
        self.txData = ScheduledTx()
        self.cfrData = ChannelConditions()
        self.pms = Pms()

    def __str__(self):
        return '%s%s%s' % (self.txData, self.cfrData, self.pms)

    def decode73(self, line, rFile):
        self.txData.decode73(line, rFile)


    def getPrintHeader(self):
        return '%s, %s, %s\n' % (ScheduledTx().getPrintHeader(), ChannelConditions().getPrintHeader(),
                               Pms().getPrintHeader())


class ChannelConditions:
    def __init__(self, ri=0, riBitWidth=0, cfrLength=0, cfrFormat=0, dlBandwidth=0,
                 cfr=[0] * MAX_CFR_INDEX, reportType=0, fileLineNo=0):
        self.ri = ri
        self.riBitWidth = riBitWidth
        self.cfrLength = cfrLength
        self.cfrFormat = cfrFormat
        self.dlBandwidth = dlBandwidth
        self.cfr = cfr
        self.cqi = [0, 0]
        self.pmi4tx = 0
        self.pmi2tx = 0
        self.reportType = reportType
        self.fileLineNo = fileLineNo

        if dlBandwidth != 0:
            self.decode_cfr()

    def __str__(self):
        if Settings.printPretty == 1:
            return 'reportType=%d, ri=%d, cfrformat=%d, dlBW=%d, cfr[0:4]=%d/%d/%d/%d cqi=%d/%d, pmi=%d/%d, fileLineNo=%d, ' % \
                   (self.reportType, self.ri, self.cfrFormat, self.dlBandwidth, self.cfr[0],
                    self.cfr[1], self.cfr[2], self.cfr[3], self.cqi[0], self.cqi[1], self.pmi4tx, self.pmi2tx, self.fileLineNo)
        else:
            return '%d, ' * 13 % \
                   (self.reportType, self.ri, self.cfrFormat, self.dlBandwidth, self.cfr[0],
                    self.cfr[1], self.cfr[2], self.cfr[3], self.cqi[0], self.cqi[1], self.pmi4tx, self.pmi2tx, self.fileLineNo)


    def getPrintHeader(self):
        return 'reportType, ri, cfrformat, dlBW, cfr[0], cfr[1], cfr[2], cfr[3], cqi[0], cqi[1], pmi4Tx, pmi2Tx, fileLineNo'

    def decode_cfr(self):

        numSubbands = PRB_TO_NUM_SUBBAND_TABLE[self.dlBandwidth]

        longCfr = (self.cfr[0] << 48) + (self.cfr[1] << 32) + (self.cfr[2] << 16) + (self.cfr[3])

        if self.reportType == PUSCH_MEAS_REPORT:
            self.decode_pusch_cqi(longCfr, numSubbands)
        elif self.reportType == PUCCH_MEAS_REPORT:
            print 'Error: we do not yet tested PUCCH reports'
            self.decode_pucch_cqi(longCfr)
        else:
            print 'Error: unknown report type %d' % self.reportType

        self.decode_pmi(longCfr)
        return

    def decode_pusch_cqi(self, longCfr, numSubbands):
        if self.cfrFormat == 9:
            # removes the cqi values from the cfr report based on bandwidth and report type
            self.cqi[0] = (self.cfr[0] >> 12) & WIDEBAND_CQI_BITMASK
            if self.ri >= 2:
                self.cqi[1] = (longCfr >> (64 - (NUM_WIDEBAND_CQI_BITS * 2 + numSubbands * 2))) & WIDEBAND_CQI_BITMASK

        else:
            print 'Error: cfr format is NOT a recognized format'

    def decode_pucch_cqi(self, longCfr):
        self.cqi[0] = (self.cfr[0] >> 12) & WIDEBAND_CQI_BITMASK

        if self.ri >= 2:
            self.cqi[1] = self.cqi[0]

    def decode_pmi(self, longCfr):
        self.pmi4tx = (longCfr >> (64 - self.cfrLength)) & PMI_4_TX_BITMASK
        self.pmi2tx = self.pmi4tx & PMI_2_TX_BITMASK


class ScheduledTx:
    def __init__(self, globalTime=0, bbUeRef=0, rnti=0, duId=0, sfn=0, sf=0, txSf=0, nrCw=0, harqIdx=0, tbs1=0, tbs2=0,
                 prb=0, mcs1=0, mcs2=0, harq1=5, harq2=5, layers=0, cce=0, swapFlag=0, cellId=0):
        self.globalTime = globalTime
        self.bbUeRef = bbUeRef
        self.rnti = rnti
        self.duId = duId
        self.sfn = sfn
        self.txSf = txSf
        self.sf = sf
        self.nrCw = nrCw
        self.harqIdx = harqIdx
        self.tbs = []
        self.tbs.append(tbs1)
        self.tbs.append(tbs2)
        self.prb = prb
        self.mcs = []
        self.mcs.append(mcs1)
        self.mcs.append(mcs2)
        self.harqFdbk = []
        self.harqFdbk.append(harq1)
        self.harqFdbk.append(harq2)
        self.harqFdbkLineNo = 0
        self.redundancyVer = [0, 0]
        self.reTxAttempt = [0, 0]
        self.layers = layers
        self.cce = cce
        self.swapFlag = swapFlag
        self.cellId = cellId
        self.nBundled = 1
        self.fileLineNo = 0

    def __str__(self):

        if Settings.printPretty:
            return '%s, bbUeRef=%s, rnti=%s, duId=%s, cellId=%s, sfn=%d, sf=%d, nrCw=%s, harqIdx=%s, tbs[0,1]=%s,%s, ' \
                   'prb=%s, mcs[0,1]=%s,%s, harqFdBk=%d/%d, harqFdbkLineNo=%d, layers=%s, cce=%s, swap=%s, ' \
                   'nBundled=%d, fileLine=%d, ' % \
                   (self.globalTime, self.bbUeRef, self.rnti, self.duId, self.cellId, self.sfn, self.txSf, self.nrCw,
                    self.harqIdx, self.tbs[0], self.tbs[1], self.prb, self.mcs[0], self.mcs[1], self.harqFdbk[0],
                    self.harqFdbk[1], self.harqFdbkLineNo, self.layers, self.cce, self.swapFlag, self.nBundled, self.fileLineNo)
        else:
            return '%d, ' * 22 % \
                   (self.globalTime, self.bbUeRef, self.rnti, self.duId, self.cellId, self.sfn, self.txSf, self.nrCw,
                    self.harqIdx, self.tbs[0], self.tbs[1], self.prb, self.mcs[0], self.mcs[1], self.harqFdbk[0],
                    self.harqFdbk[1], self.harqFdbkLineNo, self.layers, self.cce, self.swapFlag, self.nBundled, self.fileLineNo)


    def getPrintHeader(self):
        return 'globalTime, bbUeRef, rnti, duId, cellId, sfn, txSf, nrCw, harqIdx, tbs[0], tbs[1], prb, mcs[0],' \
               ' mcs[1], harqFdbk[0], harqFdbk[1], harqFdbkLineNo, layers, cce, swapFlag, nBundled, fileLineNo'


    def decode73(self, line, rFile):
        self.globalTime = getglobaltime(line)

        sf = GET_SUBFRAME_NR_EQL.search(line)
        self.txSf = int(sf.group(1))

        sfn = GET_SFN.search(line)
        self.sfn = int(sfn.group(1))

        bbUeRef = GET_BBUEREF_EQL.search(line)
        self.bbUeRef = int(bbUeRef.group(1), 16)

        rnti = GET_RNTI_EQL.search(line)
        self.rnti = int(rnti.group(1))

        harqIdx = GET_HARQ_IDX_EQL.search(line)
        self.harqIdx = int(harqIdx.group(1))

        swap = GET_SWAPFLAG_EQL.search(line)
        self.swapFlag = int(swap.group(1))

        mcs = GET_MCS_2CW_EQL.search(line)
        tbs = GET_TBS_2CW_EQL.search(line)
        rv = GET_REDUNDANCY_VER.search(line)

        if self.swapFlag == 1:
            self.mcs[0:2] = [int(mcs.group(2)), int(mcs.group(1))]
            self.tbs[0:2] = [int(tbs.group(2)), int(tbs.group(1))]
            self.redundancyVer[0:2] = [int(rv.group(2)), int(rv.group(1))]
        else:
            self.mcs[0:2] = [int(mcs.group(1)), int(mcs.group(2))]
            self.tbs[0:2] = [int(tbs.group(1)), int(tbs.group(2))]
            self.redundancyVer[0:2] = [int(rv.group(1)), int(rv.group(2))]

        prb = GET_PRBS_EQL.search(line)
        self.prb = int(prb.group(1))

        duId = GET_DUID_EQL.search(line)
        self.duId = int(duId.group(1))

        nrCw = GET_NR_CW_EQL.search(line)
        self.nrCw = int(nrCw.group(1))

        layers = GET_LAYERS_EQL.search(line)
        self.layers = int(layers.group(1))

        cce = GET_CCES_EQL.search(line)
        self.cce = int(cce.group(1))

        cellId = GET_CELLID_EQL.search(line)
        self.cellId = int(cellId.group(1))

        self.fileLineNo = rFile.lineno()


class Pms:
    def __init__(self):
        self.bler = [0.0, 0.0]
        self.avgThroughput = [0.0, 0.0]
        self.peakThroughput = [0.0, 0.0]
        self.throughputWindow = [[0.0] * Settings.throughputWindowSize, [0.0] * Settings.throughputWindowSize]

    def __str__(self):
        if Settings.printPretty:
            return 'Bler[cw1,cw2]=[%f, %f], avgThpt[0,1]=[%f,%f], peakThpt[0,1]=[%f,%f]' % \
                   (self.bler[0] * 100, self.bler[1] * 100, self.avgThroughput[0], self.avgThroughput[1],
                    self.peakThroughput[0], self.peakThroughput[1])
        else:
            return '%f,' * 6 % (self.bler[0] * 100, self.bler[1] * 100, self.avgThroughput[0], self.avgThroughput[1],
                                self.peakThroughput[0], self.peakThroughput[1])

    def getPrintHeader(self):
        return 'bler[0], bler[1], avgThroughput[0], avgThroughput[1]'

    def calc_bler(self, prevBler, isAck, codeword, numBundledTx=1):
        forgettingFactor = Settings.forgettingFactor / numBundledTx
        self.bler[codeword] = (1-forgettingFactor) * prevBler + forgettingFactor * (1-isAck)

    def calc_throughput(self, prevPm, txBlockSize, isAck, cwIndex):
        txInKBps = (txBlockSize * isAck) / 1000
        self.throughputWindow[cwIndex][0] = txInKBps
        self.throughputWindow[cwIndex][1:Settings.throughputWindowSize] = prevPm.throughputWindow[cwIndex][0:(Settings.throughputWindowSize-1)]

        self.avgThroughput[cwIndex] = sum(self.throughputWindow[cwIndex]) / Settings.throughputWindowSize

        if prevPm.peakThroughput[cwIndex] < self.avgThroughput[cwIndex]:
            self.peakThroughput[cwIndex] = self.avgThroughput[cwIndex]
        else:
            self.peakThroughput[cwIndex] = prevPm.peakThroughput[cwIndex]


class Summary:
    
    def __init__(self):
        self.schedulingFreq = 0.0
        self.numDtx = [0, 0]
        self.numNack = [0, 0]
        self.numUnknown = [0, 0]
        self.numInvalid = [0, 0]
        self.numAck = [0, 0]
        self.numTx = [0, 0]
        self.avgMcs = [0.0, 0.0]
        self.avgTbSize = [0, 0]
        self.reTxAttemptCount = [[0, 0, 0, 0], [0, 0, 0, 0]]
        
    def __str__(self):
        cw1String = '\tCW1:\n\t\tScheduling Freq = %.2f%%, nrNack=%d, nrDtx=%d, nrUnknown=%d, nrInvalid=%d, nrTx=%d\n' \
               '\t\t%%Nack = %.2f%%, %%Dtx = %.2f%% reTxAttempts: 1st=%d, 2nd=%d, 3rd=%d reTxFailed=%d\n\t\tavgMcs = %.2f, avgTbSize = %d\n\n' %\
               (self.schedulingFreq, self.numNack[0], self.numDtx[0], self.numUnknown[0], self.numInvalid[0],
                self.numTx[0], 100.0 * self.numNack[0]/self.numTx[0], 100.0 * self.numDtx[0]/self.numTx[0],
                self.reTxAttemptCount[0][0], self.reTxAttemptCount[0][1], self.reTxAttemptCount[0][2], self.reTxAttemptCount[0][3],
                self.avgMcs[0], self.avgTbSize[0])
        cw2String = '\tCW2:\n\t\tScheduling Freq = %.2f%%, nrNack=%d, nrDtx=%d, nrUnknown=%d, nrInvalid=%d, nrTx=%d\n' \
               '\t\t%%Nack = %.2f%%, %%Dtx = %.2f%% reTxAttempts: 1st=%d, 2nd=%d, 3rd=%d reTxFailed=%d\n\t\tavgMcs = %.2f, avgTbSize = %d\n\n' %\
               (self.schedulingFreq, self.numNack[1], self.numDtx[1], self.numUnknown[1], self.numInvalid[1],
                self.numTx[1], 100.0 * self.numNack[1]/self.numTx[1], 100.0 * self.numDtx[1]/self.numTx[1],
                self.reTxAttemptCount[1][0], self.reTxAttemptCount[1][1], self.reTxAttemptCount[1][2], self.reTxAttemptCount[1][3],
                self.avgMcs[1], self.avgTbSize[1])

        return cw1String + cw2String