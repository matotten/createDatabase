import fileinput
import time
from dataBase import *

# TODO:
'''
    split up main.py into different file groupings like bbFilter does.

    Ie. decoding reports may be its own file, making PM calculations would be another etc.
'''

# TODO: add summary information. %DTX, NACK, UNKNOWN, PRB utilization, avg bler, avg throughput, avg CCE usage
# TODO: file output needs to have 0 entries in TTIs UE is not scheduled
# TODO: check encapsulation and abstraction
# TODO: test script with FDD logs
# TODO: check what happenens if we are missing certain logs?
# TODO: check if sf and txSf are used properly
# TODO: figure out how to properly add new TTI occurrences while supporting other traces
# TODO: think further about CA log considerations
# TODO: improve the throughput calculation
# TODO: look into odd output. Odd because of tbSize seems too small for MCS 27 PRB 100
''' 108, bbUeRef=2432696384, rnti=13217, duId=1, cellId=145, sfn=148, sf=6, nrCw=2, harqIdx=3, tbs[0,1]=149776,93800, prb=100, mcs[0,1]=31,27, harqFdBk=1/1, harqFdbkLineNo=37739, layers=4, cce=2, swap=1, nBundled=4, fileLine=35034, reportType=1, ri=4, cfrformat=9, dlBW=100, cfr[0:4]=49237/16639/341/1011 cqi=12/12, pmi=3/3, fileLineNo=33113, Bler[cw1,cw2]=[9.305711, 9.889172], avgThpt[0,1]=[79.000000,102.000000], peakThpt[0,1]=[133.000000,126.000000]

'''
# TODO: calculate average throughput - V1.0 done
# TODO: calculate UE scheduling frequency - V1.0 done in UE summary output
# TODO: check usage of bler swap flag - Fixed
# TODO: add in file line numbers during data collection - Fixed
# TODO: Bler for 2nd CW resets if 1CW transmission occurs, need to fix. - Fixed
# TODO: harqFdbk seems unknown when transmitting mixed 1CW 2CW bundles - Fixed
# TODO: issue, we reuse harqIdx when transmitting on 1cw. this overwrites harqIdx struct and we lose data - Fixed

start_time = time.time()

cellDatabase = {}

HARQ_INDICATION_INVALID = 15

measTime = 0

measCnt = 0


'''
getUe: takes bbUeRef in decimal NOT hex. cellId is a string. will return the UeData object for the given bbUeRef and
cellId combination if there is no object already in the database, getUe will create a UeData object for that UE
'''
def get_ue(bbUeRef, cellId):
    """
    :param bbUeRef - in decimal
            cellId - as a String:
    :return: UeData object
    """
    if cellId in cellDatabase.keys():
        if bbUeRef not in cellDatabase[cellId].keys():
            newUe = UeData()
            cellDatabase[cellId][bbUeRef] = newUe
    else:
        cellDatabase[cellId] = {bbUeRef: UeData()}

    return cellDatabase[cellId][bbUeRef]


'''
parseHarqFeedback - will read the harq feedback report. Once report is decoded it will find the UE in the UE database
and update harq information for relevant transmission.
'''
def parse_harq_fdbk(line):
    # get data from current line
    globalTime = getglobaltime(line)

    nrOfReports = 0

    for newLine in rFile:

        # if there is no digits there is no data to pull, therefore we try next line
        if not HAS_DIGIT:
            continue
        elif SUBFRAME_NO.search(newLine):
            sf = GET_FIRST_DIGITS.search(newLine)
            sf = sf.group(1)
        elif CELLID.search(newLine):
            cellId = GET_FIRST_DIGITS.search(newLine)
            cellId = cellId.group(1)
        elif NR_PUCCH_RPT.search(newLine):
            nrOfPucchReports = GET_FIRST_DIGITS.search(newLine)
            nrOfReports += int(nrOfPucchReports.group(1))
            if nrOfReports == 0:
                return
        elif NR_PUSCH_RPT.search(newLine):
            nrOfPuschReports = GET_FIRST_DIGITS.search(newLine)
            nrOfReports += int(nrOfPuschReports.group(1))
        elif BBUEREF.search(newLine):
            bbUeRef = GET_FIRST_DIGITS.search(newLine)
            bbUeRef = int(bbUeRef.group(1))
        elif HARQ_VALID.search(newLine):
            dlHarqValid = GET_FIRST_DIGITS.search(newLine)
            dlHarqValid = dlHarqValid.group(1)
        elif HARQ_PROC_ID.search(newLine):
            dlHarqProcessId = GET_FIRST_DIGITS.search(newLine)
            dlHarqProcessId = int(dlHarqProcessId.group(1))
        elif NR_TB.search(newLine):
            nrOfTb = GET_FIRST_DIGITS.search(newLine)
            nrOfTb = nrOfTb.group(1)
        elif HARQ_FDBK_IND.search(newLine):
            detectedHarqIndication = GET_FIRST_DIGITS.search(newLine)
            harqId = int(detectedHarqIndication.group(1))

            if dlHarqValid == '1':
                # TODO
                if Settings.isHarqFeedback == 0:
                    Settings.isHarqFeedback = 1
                ueData = get_ue(bbUeRef, cellId)

                if Settings.isTdd:
                    ueData.set_harq_tdd(globalTime, dlHarqProcessId, harqId, rFile.lineno())
                else:
                    ueData.set_harq_fdd(globalTime, dlHarqProcessId, harqId, rFile.lineno())

                nrOfReports -= 1
                if nrOfReports == 0:
                    return
            elif detectedHarqIndication == HARQ_INDICATION_INVALID:
                print 'Error: expected a valid Harq Feedback report'
                return


def parse_measurementreport(line):

    # get data from current line
    #globalTime = getglobaltime(line)

    nrOfReports = 0
    lastReport = 0

    for newLine in rFile:
        if SRS_RPT_LIST.search(newLine):
            return
        elif PUSCH_RPT_LIST.search(newLine):
            lastReport = PUSCH_MEAS_REPORT
        elif PUCCH_RPT_LIST.search(newLine):
            lastReport = PUCCH_MEAS_REPORT
        elif not HAS_DIGIT.search(newLine):
            continue
        elif SUBFRAME_NO.search(newLine):
            sf = GET_FIRST_DIGITS.search(newLine)
            sf = sf.group(1)
        elif CELLID.search(newLine):
            cellId = GET_FIRST_DIGITS.search(newLine)
            cellId = cellId.group(1)
        elif NR_PUCCH_RPT.search(newLine):
            nrOfPucchReports = GET_FIRST_DIGITS.search(newLine)
            nrOfReports += int(nrOfPucchReports.group(1))

            if nrOfReports == 0:
                return
        elif NR_PUSCH_RPT.search(newLine):
            nrOfPuschReports = GET_FIRST_DIGITS.search(newLine)
            nrOfReports += int(nrOfPuschReports.group(1))
        elif BBUEREF.search(newLine):
            bbUeRef = GET_FIRST_DIGITS.search(newLine)
            bbUeRef = int(bbUeRef.group(1))
        elif IS_DTX.search(newLine):
            isDtx = GET_FIRST_DIGIT.search(newLine)
            isDtx = int(isDtx.group(1))
        elif RANK.search(newLine):
            ri = GET_FIRST_DIGIT.search(newLine)
            ri = int(ri.group(1))
        elif RANK_BIT_WIDTH.search(newLine):
            riBitWidth = GET_FIRST_DIGIT.search(newLine)
            riBitWidth = int(riBitWidth.group(1))
        elif CFR_LENGTH.search(newLine):
            cfrLength = GET_FIRST_DIGITS.search(newLine)
            cfrLength = int(cfrLength.group(1))
        elif CFR_FORMAT.search(newLine):
            cfrFormat = GET_FIRST_DIGITS.search(newLine)
            cfrFormat = int(cfrFormat.group(1))
        elif CFR_VALID.search(newLine):
            cfrValid = GET_FIRST_DIGITS.search(newLine)
            cfrValid = int(cfrValid.group(1))
        elif CFR_CRC_FLAG.search(newLine):
            cfrCrcFlag = GET_FIRST_DIGIT.search(newLine)
            cfrCrcFlag = int(cfrCrcFlag.group(1))
        elif BANDWIDTH.search(newLine):
            dlBandwidth = GET_FIRST_DIGITS.search(newLine)
            dlBandwidth = int(dlBandwidth.group(1))
        elif CFR_WDIGIT.search(newLine):
            cfr = GET_FIRST_DIGITS.search(newLine)
            cfrReport = [0] * MAX_CFR_INDEX
            cfrReport[0] = int(cfr.group(1))
            cfr = GET_CFR.search(next(rFile))
            if cfr is not None:
                cfrReport[1] = int(cfr.group(1))
            cfr = GET_CFR.search(next(rFile))
            if cfr is not None:
                cfrReport[2] = int(cfr.group(1))
            cfr = GET_CFR.search(next(rFile))
            if cfr is not None:
                cfrReport[3] = int(cfr.group(1))

            if cfrValid == 1 and cfrCrcFlag == 1:

                ueData = get_ue(bbUeRef, cellId)
                temp = time.time()
                cfrData = ChannelConditions(ri, riBitWidth, cfrLength, cfrFormat, dlBandwidth, cfrReport,
                                            lastReport, rFile.lineno())
                global measTime
                measTime += time.time() - temp
                global measCnt
                measCnt += 1
                ueData.add_cfr_data(cfrData)

                nrOfReports -= 1
                if nrOfReports == 0:
                    return


def parse_upcdl73(line, rFile):
    result = re.search(r'cellId=(\d+)', line)
    cellId = result.group(1)

    result = re.search(r'bbUeRef=(\w+)', line)
    bbUeRef = int(result.group(1), 16)

    ueData = get_ue(bbUeRef, cellId)
    ueData.decode73(line, rFile)


def print_summary():
    if Settings.testRun == 0:
        wSummaryFile = open('testSummary.txt', 'w+')
    ueString = ''
    for cellId in cellDatabase.keys():
        for ueRef in cellDatabase[cellId]:
            if ueRef == 0:
                continue
            ue = cellDatabase[cellId][ueRef]
            ue.update_uesummary()
            ueString += 'BbUeRef = %#x: Summary Information\n' % ueRef
            ueString += str(ue.summary)


    if Settings.testRun == 0:
        wSummaryFile.write(ueString)
        wSummaryFile.close()
    else:
        print ueString


def print_database():

    printString = ''
    if not Settings.printPretty:
        if Settings.testRun:
            Settings.printPretty = 1
        printString += str(TtiOccurrence().getPrintHeader())
    for cellId in cellDatabase.keys():
        for ueRef in cellDatabase[cellId]:
            if ueRef == 0:
                continue
            ue = cellDatabase[cellId][ueRef]
            ue.update_bler()
            ue.update_throughput()
            printString += str(ue)

    if Settings.testRun:
        print printString
    else:
        wFile = open("testOutput.csv", 'w+')
        wFile.write(printString)
        wFile.close()

# start of Main function
#rFile = fileinput.input("testFile.txt")
rFile = fileinput.input("xab.txt")


upcdl73 = re.compile(r"UPCDL.73")
harqFeedbackRpt = re.compile(r"LPP_UP_ULMACPE_CI_UL_L1_HARQFDBK2_DL_IND")
ulMeasurementReport = re.compile(r'LPP_UP_ULMACPE_CI_UL_L1_MEASRPRT2_DL_IND')
startOfLog = re.compile(r'\[')

count = 0
upcCount = 0
upcTime = 0

measurCount = 0
measurTime = 0

harqCount = 0
harqTime = 0

tempTime = 0

printTime = 0
printSummaryTime = 0


for line in rFile:

    if line[0] is not '[':
        continue
    elif harqFeedbackRpt.search(line):
        tempTime = time.time()
        parse_harq_fdbk(line)
        harqTime += float(time.time() - tempTime)
        harqCount += 1
    elif upcdl73.search(line):
        tempTime = time.time()
        parse_upcdl73(line, rFile)
        upcTime += float(time.time() - tempTime)
        upcCount += 1
    elif ulMeasurementReport.search(line):
        tempTime = time.time()
        parse_measurementreport(line)
        measurTime += float(time.time() - tempTime)
        measurCount += 1

    count += 1

    if Settings.testRun and rFile.lineno() >= 50000:
        break
rFile.close()

tempTime = time.time()
print_database()
printTime = time.time() - tempTime

if Settings.printSummary:
    tempTime = time.time()
    print_summary()
    printSummaryTime = time.time() - tempTime



print "--- %s seconds ---" % (time.time() - start_time)
print "--- upc=%f, measr=%f, harq=%f ---" % (upcTime/upcCount, measurTime/measurCount, harqTime/harqCount)
print "--- upcC=%d, measrC=%d, harqC=%d ---" % (upcCount, measurCount, harqCount)
print "--- upcT=%f, measrT=%f, harqT=%f ---" % (upcTime, measurTime, harqTime)
print "--- printTime = %s summaryTime = %s seconds ---" % (printTime, printSummaryTime)

print "measrT=%f" % float(measTime/measCnt)