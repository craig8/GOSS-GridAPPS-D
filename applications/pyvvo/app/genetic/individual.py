"""
required packages: pyodbc

Created on Aug 9, 2017

@author: thay838
"""
import random
from glm import modGLM
import util.gld
import util.helper
import util.constants
import util.db
import math
import os
import copy

# Define cap status, to be accessed by binary indices.
CAPSTATUS = ['OPEN', 'CLOSED']
# Define the percentage of the tap range which sigma should be for drawing
# tap settings. Recall the 68-95-99.7 rule for normal distributions -
# 1 std dev, 2 std dev, 3 std dev probabilities
TAPSIGMAPCT = 0.1
# Define mode of triangular distribution for biasing capacitors. NOTE: By
# making the mode greater than 0.5, we're more likely to draw a number which
# rounds to one. Therefore, we should maintain the previous state if the draw
# rounds to one.
CAPTRIANGULARMODE = 0.8
 
class individual:
    
    def __init__(self, uid, starttime, stoptime, timezone, database, voltFiles,
                 reg=None, regFlag=5, cap=None, capFlag=5, regChrom=None, 
                 capChrom=None, parents=None, controlFlag=0,
                 recordInterval=60, gldPath=None):
        """An individual contains information about Volt/VAR control devices
        
        Individuals can be initialized in two ways: 
        1) From scratch: Provide self, uid, reg, and cap inputs. Positions
            will be randomly generated
            
        2) From a chromosome: Provide self, reg, cap, uid, regChrom, and 
            capChrom. After crossing two individuals, a new chromosome will
            result. Use this chromosome to update reg and cap
        
        INPUTS:
            starttime: datetime object for model start
            stoptime: "..." end 
            timezone: string representing timezone, as it would appear in 
                GridLAB-D's tzinfo.txt. Example: 'PST+8PDT'
            database: Dictionary to be passed to the util/db.db class
                constructor. NOTE: 
            voltFiles: list of filenames of files which monitor voltage. 
                Should be output from group_recorder. Used to evaluate voltage
                violations.
            reg: Dictionary as described in the docstring for the gld module.
            
                Note possible tap positions be in interval [-lower_taps,
                raise_taps].
            
            regFlag: Flag for special handling of regulators.
                0: All regulator taps set to their minimum tap position
                1: All regulator taps set to their maximum tap position
                2: Regulator tap positions will be biased (via a Gaussian 
                    distribution and the TAPSIGMAPCT constant) toward the
                    previous tap positions
                3: Regulator state unchanged - simply reflects what's in the 
                    reg input's 'prevState'
                4: Regulator state given in reg input's 'newState' - just need
                    to generate chromosome and count tap changes
                5: Regulator tap positions will be determined randomly 
                    
            cap: Dictionary describing capacitors as described in the docstring
                for the gld module.
                
            capFlag: Flag for special handling of capacitors.
                0: All capacitors set to CAPSTATUS[0] (OPEN)
                1: All capacitors set to CAPSTATUS[1] (CLOSED)
                2: Capacitor states will be biased (via a triangular
                    distribution with the mode at CAPTRIANGULARMODE) toward the
                    previous states
                3: Capacitor state unchanged - simply reflects what's in the
                    'cap' input's 'prevState'.
                4: Capacitor state given in cap input's 'newState' - just need
                    to generate chromosome and count switching events
                5: Capacitor positions will be determined randomly.
                
            uid: Unique ID of individual. Should be an int.
            
            regChrom: Regulator chromosome resulting from crossing two
                individuals. List of ones and zeros representing tap positions. 
                
            capChrom: Capacitor chromosome resulting from crossing two
                individuals. List of ones and zeros representing switch status.
                
            parents: Tuple of UIDs of parents that created this individual.
                None if individual was randomly created at population init.
                
            controlFlag: Flag to determine the control scheme used in an 
                individual's model. This will also affect how evaluation is
                performed. For example, a model with volt_var_control has to
                calculate it's tap changes and capacitor switching events after
                a model has been run, while a manual control scheme computes
                tap changing/switching before running its model.
                Possible inputs (more to come later, maybe):
                0: Manual control of regulators and capacitors
                1: Output voltage control of regulators and capacitors
                2: Output voltage control of regulators, VAR control of
                    capacitors
                3: Output voltage control of regulators, VARVOLT control of
                    capacitors
                4: volt_var_control of regulators and capacitors. This will
                    create a volt_var_control object, and set regs and caps to
                    MANUAL to avoid letting them switch at initialization
                
            NOTE: If the controlFlag is not 0, the regFlag and capFlag must
                be set to 3. 
            
        TODO: add controllable DERs
                
        """
        # Ensure flags are compatible.
        if controlFlag:
            assert capFlag == regFlag == 3
        
        # Initialize some attributes that also need reset when re-using an
        # individual.
        self.prep(starttime=starttime, stoptime=stoptime)
        
        # Set the timezone (this isn't done in prep function as it's assumed
        # to never change for an individual - feeders don't get up and move, 
        # and timezones don't often change.
        self.timezone = timezone
        
        # Assign gldPath
        self.gldPath = gldPath
        
        # set database object
        self.dbObj = util.db.db(**database)
        
        # Set the control flag
        self.controlFlag = controlFlag
        
        # Assign voltFiles
        self.voltFiles = voltFiles
        
        # Assign reg and cap dicts. Perform a deepcopy, since an individual
        # will modify its own copy of the given reg and cap definitions.
        self.reg = copy.deepcopy(reg)
        self.cap = copy.deepcopy(cap)
        
        # Assign the unique identifier.
        self.uid = uid
        
        # Parent tracking is useful to see how well the GA is working
        self.parents = parents
        
        # Recording inverval
        self.recordInterval = recordInterval
        
        # When writing model, output directory will be saved.
        self.outDir = None
        
        # If not given a regChrom or capChrom, generate them.
        if (regChrom is None) and (capChrom is None):
            # Generate regulator chromosome:
            self.genRegChrom(flag=regFlag)
            # Generate capacitor chromosome:
            self.genCapChrom(flag=capFlag)
            # TODO: DERs
        else:
            # Use the given chromosomes to update the dictionaries.
            self.regChrom = regChrom
            self.modifyRegGivenChrom()
            self.capChrom = capChrom
            self.modifyCapGivenChrom()
            
    def prep(self, starttime, stoptime, reg=None, cap=None):
        """Method to get an individual ready for use/re-use - in the genetic
            algorithm, the population for the next time interval should be
            seeded with the best individuals from the previous time interval.
            
        During a call to the constructor, this gets attributes initialized.
        
        Pass in 'reg' and 'cap' ONLY to get an individual ready to be used in
        a new population.
        """
        # Assing times.
        self.starttime = starttime
        self.start_str = starttime.strftime(util.constants.DATE_TZ_FMT)
        self.stoptime = stoptime
        self.stop_str = stoptime.strftime(util.constants.DATE_TZ_FMT)
        # Full path to output model.
        self.model = None
        # Table information
        self.swingData = None
        self.regData = None
        self.capData = None
        
        # When the model is run, output will be saved.
        self.modelOutput = None

        # The evalFitness method assigns costs
        self.costs = None
        
        # Update the 'prevState' of the individuals reg and cap dictionaries.
        if reg and cap:
            out = util.helper.updateVVODicts(regOld=self.reg, capOld=self.cap,
                                             regNew=reg, capNew=cap)
            
            self.reg = out['reg']
            self.cap = out['cap']
            self.tapChangeCount = out['tapChangeCount']
            self.capSwitchCount = out['capSwitchCount']
        else:
            # Track tap changes and capacitor switching
            self.tapChangeCount = 0
            self.capSwitchCount = 0
            
    def __eq__(self, other):
        """Compare individuals by looping over their chromosomes
        
        TODO: This isn't very sophisticated. It doesn't check if chromosomes
        are the same length, exist, etc.
        """
        # Start with regulator
        for k in range(len(self.regChrom)):
            if self.regChrom[k] != other.regChrom[k]:
                return False
            
        # On to capacitor
        for k in range(len(self.capChrom)):
            if self.capChrom[k] != other.capChrom[k]:
                return False
            
        return True
        
            
    def __str__(self):
        """Individual's string should include fitness and reg/cap info.
        
        This is a simple wrapper to call helper.getSummaryStr since the
        benchmark system should be displayed in the same way.
        """
        s = util.helper.getSummaryStr(costs=self.costs, reg=self.reg,
                                      cap=self.cap, regChrom=self.regChrom,
                                      capChrom=self.capChrom,
                                      parents=self.parents)
        
        return s
        
    def genRegChrom(self, flag, updateCount=True):
        """Method to randomly generate an individual's regulator chromosome
        
        INPUTS:
            flag: dictates how regulator tap positions are created.
                0: All regulator taps set to their minimum tap position
                1: All regulator taps set to their maximum tap position
                2: Regulator tap positions will be biased (via a Gaussian 
                    distribution and the TAPSIGMAPCT constant) toward the
                    previous tap positions
                3: Regulator state unchanged - simply reflects what's in the 
                    reg input's 'prevState'
                4: Regulator state given in reg input's 'newState' - just need
                    to generate chromosome and count tap changes
                5: Regulator tap positions will be determined randomly 
            updateCount: Flag (True or False) to indicate whether or not the
                individual's tapChangeCount should be updated. When using this
                function to generate an individual, this should generally be
                set to True. However, when updating a baseline model (like one
                that uses volt_var_control) which computes its tap changes 
                elsewhere, set updateCount to False.
        """
        # Initialize chromosome for regulator and dict to store list indices.
        self.regChrom = ()
         
        # Intialize index counters.
        s = 0;
        e = 0;
        
        # Loop through the regs and create binary representation of taps.
        for r, v in self.reg.items():
            
            # Define the upper tap bound (tb).
            tb = v['raise_taps'] + v['lower_taps']
            
            # Compute the needed field width to represent the upper tap bound
            # Use + 1 to account for 2^0
            width = math.ceil(math.log(tb, 2)) + 1
            
            # Define variables as needed based on the flag. I started to try to
            # make micro-optimizations for code factoring, but let's go for
            # readable instead.
            if flag== 0:
                newState = 0
            elif flag == 1:
                newState = tb
            elif flag == 2:
                # If we're biasing from the previous position, get a sigma for
                # the Gaussian distribution.
                tapSigma = round(TAPSIGMAPCT * (tb + 1))
            elif flag == 3:
                state = 'prevState'
            elif flag == 4:
                state = 'newState'
            
            # Loop through the phases
            for phase, phaseData in v['phases'].items():
                
                # If we're biasing new positions based on previous positions:
                if flag == 2:
                    # Randomly draw tap position from gaussian distribution.
                    
                    # Translate previous position to integer on interval [0,tb]
                    prevState = \
                        util.gld.inverseTranslateTaps(lowerTaps=v['lower_taps'],
                                                 pos=phaseData['prevState'])
                        
                    # Initialize the newState for while loop.
                    newState = -1
                    
                    # The standard distribution runs from (-inf, +inf) - draw 
                    # until position is valid. Recall valid positions are
                    # [0, tb]
                    while (newState < 0) or (newState > tb):
                        # Draw the tap position from the normal distribution.
                        # Here oure 'mu' is the previous value
                        newState = round(random.gauss(prevState, tapSigma))
                        
                elif (flag == 3) or (flag == 4):
                    # Translate position to integer on interval [0, tb]
                    newState = \
                        util.gld.inverseTranslateTaps(lowerTaps=v['lower_taps'],
                                                      pos=phaseData[state])
                        
                elif flag == 5:
                    # Randomly draw.
                    newState = random.randint(0, tb)
                
                # Express tap setting as binary list with consistent width.
                binTuple = tuple([int(x) for x in "{0:0{width}b}".format(newState,
                                                                  width=width)])
                
                # Extend the regulator chromosome.
                self.regChrom += binTuple
                
                # Increment end index.
                e += len(binTuple)
                
                # Translate newState for GridLAB-D.
                self.reg[r]['phases'][phase]['newState'] = \
                    util.gld.translateTaps(lowerTaps=v['lower_taps'], pos=newState)
                    
                # Increment the tap change counter (previous pos - this pos)
                if updateCount:
                    self.tapChangeCount += \
                        abs(self.reg[r]['phases'][phase]['prevState']
                            - self.reg[r]['phases'][phase]['newState'])
                
                # Assign indices for this phase
                self.reg[r]['phases'][phase]['chromInd'] = (s, e)
                
                # Increment start index.
                s += len(binTuple)
                
    def genCapChrom(self, flag, updateCount=True):
        """Method to generate an individual's capacitor chromosome.
        
        INPUTS:
            flag:
                0: All capacitors set to CAPSTATUS[0] (OPEN)
                1: All capacitors set to CAPSTATUS[1] (CLOSED)
                2: Capacitor states will be biased (via a triangular
                    distribution with the mode at CAPTRIANGULARMODE) toward the
                    previous states
                3: Capacitor state unchanged - simply reflects what's in the
                    'cap' input's 'prevState'.
                4: Capacitor state given in cap input's 'newState' - just need
                    to generate chromosome and count switching events
                5: Capacitor positions will be determined randomly.
            updateCount: Flag (True or False) to indicate whether or not the
                individual's capSwitchCount should be updated. When using this
                function to generate an individual, this should generally be
                set to True. However, when updating a baseline model (like one
                that uses volt_var_control) which computes its switch changes 
                elsewhere, set updateCount to False.
                
                
        OUTPUTS:
            modifies self.cap, sets self.capChrom
        """
        # If we're forcing all caps to the same status, determine the binary
        # representation. TODO: add input checking.
        if flag < 2:
            capBinary = flag
            capStatus = CAPSTATUS[flag]
        elif flag == 3:
            state = 'prevState'
        elif flag == 4:
            state = 'newState'
        
        # Initialize chromosome for capacitors and dict to store list indices.
        self.capChrom = ()

        # Keep track of chromosome index
        ind = 0
        
        # Loop through the capacitors, randomly assign state for each phase
        for c, capData in self.cap.items():
            
            # Loop through the phases and randomly decide state
            for phase in capData['phases']:
                
                # Take action based on flag.
                if flag == 2:
                    # Use triangular distribution to bias choice
                    draw = round(random.triangular(mode=CAPTRIANGULARMODE))
                    
                    # Extract the previous state
                    prevState = self.cap[c]['phases'][phase]['prevState']
                    
                    # If the draw rounded to one, use the previous state.
                    # If the draw rounded to zero, use the opposite state
                    if draw:
                        capStatus = prevState
                        capBinary = CAPSTATUS.index(capStatus)
                    else:
                        # Flip the bit
                        capBinary = 1 - CAPSTATUS.index(prevState) 
                        capStatus = CAPSTATUS[capBinary]
                        
                elif (flag == 3) or (flag == 4):
                    # Use either 'prevState' or 'newState' for this state
                    capStatus = self.cap[c]['phases'][phase][state]
                    capBinary = CAPSTATUS.index(capStatus)
                elif flag == 5:
                    # Randomly determine state
                    capBinary = round(random.random())
                    capStatus = CAPSTATUS[capBinary]
                    
                # Assign to the capacitor
                self.capChrom += (capBinary,)
                self.cap[c]['phases'][phase]['newState'] = capStatus
                self.cap[c]['phases'][phase]['chromInd'] = ind
                
                # Increment the switch counter if applicable
                if (updateCount
                    and ((self.cap[c]['phases'][phase]['newState']
                          != self.cap[c]['phases'][phase]['prevState']))):
                    
                    self.capSwitchCount += 1
                
                # Increment the chromosome counter
                ind += 1
                
    def modifyRegGivenChrom(self):
        """Modifiy self.reg based on self.regChrom
        """
        # Loop through self.reg and update 'newState'
        for r, regData in self.reg.items():
            for phase, phaseData in regData['phases'].items():
                
                # Extract the binary representation of tap position.
                tapBin = \
                    self.regChrom[phaseData['chromInd'][0]:\
                                  phaseData['chromInd'][1]]
                    
                # Convert the binary to an integer
                posInt = util.helper.bin2int(tapBin)
                
                # Convert integer to tap position and assign to new position
                self.reg[r]['phases'][phase]['newState'] = \
                    util.gld.translateTaps(lowerTaps=self.reg[r]['lower_taps'],
                                      pos=posInt)
                    
                # Increment the tap change counter (previous pos - this pos)
                self.tapChangeCount += \
                    abs(self.reg[r]['phases'][phase]['prevState']
                        - self.reg[r]['phases'][phase]['newState'])
    
    def modifyCapGivenChrom(self):
        """Modify self.cap based on self.capChrom
        """
        # Loop through the capDict and assign 'newState'
        for c, capData in self.cap.items():
            for phase in capData['phases']:
                # Read chromosome and assign newState
                self.cap[c]['phases'][phase]['newState'] = \
                    CAPSTATUS[self.capChrom[self.cap[c]['phases'][phase]\
                                            ['chromInd']]]
                
                # Bump the capacitor switch count if applicable
                if self.cap[c]['phases'][phase]['newState'] != \
                        self.cap[c]['phases'][phase]['prevState']:
                    
                    self.capSwitchCount += 1
                
    def writeModel(self, strModel, inPath, outDir, recordInterval=None):
        """Create a GridLAB-D .glm file for the given individual by modifying
        setpoints for controllable devices (capacitors, regulators, eventually
        DERs)
        
        INPUTS:
            self: constructed individual
            strModel: string of .glm file found at inPath
            inPath: path to model to modify control settings
            outDir: directory to write new model to. Filename will be inferred
                from the inPath, and the individuals uid preceded by an
                underscore will be added
            dumpGroup: Name of group used for triplex_loads.
            recordInterval: Interval to record things like energy, tapchange,
                capswitch, etc. which typically only need recorded once per
                model. If None, the difference between stoptime and starttime
                will be used (so we only record once)
                
        OUTPUTS:
            Path to new model after it's created
        """
        if not recordInterval:
            # Get the model runtime - we only need to record regulator tap 
            # changes and capacitor changes at the end of simulation.
            modelDelta = (util.helper.dtToUTC(self.stoptime)
                          - util.helper.dtToUTC(self.starttime))
            recordInterval = modelDelta.total_seconds()
            
        # Check if directory exists - if not, create it.
        if not os.path.isdir(outDir):
            os.mkdir(outDir)
        
        # Assign output directory.
        self.outDir = outDir
        
        # Get the filename of the original model and create output path
        model = \
            modGLM.modGLM.addFileSuffix(inPath= os.path.basename(inPath),
                                            suffix=str(self.uid))
        
        # Track the output path for running the model later.
        self.model = model
        
        # Instantiate a modGLM object.
        writeObj = modGLM.modGLM(strModel=strModel, pathModelIn=inPath,
                                pathModelOut=(outDir + '/' + model))
        
        # Update the clock
        writeObj.updateClock(starttime=self.start_str, stoptime=self.stop_str,
                             timezone=self.timezone)
        
        # Update the swing node to a meter and get it writing power to a table
        # TODO: swing table won't be the only table.
        # Compute
        o = writeObj.recordSwing(suffix=self.uid,
                                 powerInterval=self.recordInterval,
                                 energyInterval=recordInterval)
        self.swingData = o
        
        # TODO: Uncomment when ready
        '''
        # Record triplex nodes
        o = writeObj.recordTriplex(suffix=self.uid)
        self.triplexTable = o['table']
        self.triplexColumns = o['columns']
        self.triplexInterval = o['interval']
        ''' 
        
        # Take control specific actions.
        if self.controlFlag == 0:
            regControl = 'MANUAL'
            capControl = 'MANUAL'
        elif (self.controlFlag > 0):
            # Need to record regulators and capacitors to track state changes
            # and ending positions. Define necessary data.
            self.capData = {'table': 'cap_' + str(self.uid),
                            'changeColumns': util.gld.CAP_CHANGE_PROPS,
                            'stateColumns': util.gld.CAP_STATE_PROPS,
                            'interval': recordInterval}
            
            self.regData = {'table': 'reg_' + str(self.uid),
                            'changeColumns': util.gld.REG_CHANGE_PROPS,
                            'stateColumns': util.gld.REG_STATE_PROPS,
                            'interval': recordInterval}
            
            if self.controlFlag == 1:
                regControl = 'OUTPUT_VOLTAGE' 
                capControl = 'VOLT'
            elif self.controlFlag == 2:
                regControl = 'OUTPUT_VOLTAGE' 
                capControl = 'VAR'
            elif self.controlFlag == 3:
                regControl = 'OUTPUT_VOLTAGE' 
                capControl = 'VARVOLT'
            elif self.controlFlag == 4:
                # If we're looking at a VVO scheme, we need to add a VVO
                # object.
                # TODO: This is SUPER HARD-CODED to only work for the
                # R2-12-47-2 feeder. Eventually, this needs made more flexible.
                
                # Set controls to MANUAL to avoid devices switching on
                # initialization.
                regControl = 'MANUAL'
                capControl = 'MANUAL'
                # NOTE: this method creates a player file... annoying.
                self.vvoPlayer = writeObj.addVVO(starttime=self.start_str)
            
        # Set regulator and capacitor control schemes, and add recorders if
        # necessary.
        for r in self.reg:
            # Modify control setting
            self.reg[r]['Control'] = regControl
            
            # Add recorders if needed
            if self.controlFlag > 0:
                writeObj.addMySQLRecorder(parent=r,
                                          table=self.regData['table'],
                                          properties=(self.regData['changeColumns']
                                                      + self.regData['stateColumns']),
                                          interval=self.regData['interval'])
                
        for c in self.cap:
            # Modify control settings
            self.cap[c]['control'] = capControl
            
            # Add recorders if needed
            if self.controlFlag > 0:
                writeObj.addMySQLRecorder(parent=c,
                                          table=self.capData['table'],
                                          properties=(self.capData['changeColumns']
                                                      + self.capData['stateColumns']),
                                          interval=self.capData['interval'])
            
        # Change capacitor and regulator statuses/positions and control.
        writeObj.commandRegulators(reg=self.reg)
        writeObj.commandCapacitors(cap=self.cap)
        
        # Write the modified model to file.
        writeObj.writeModel()
    
    def runModel(self):
        """Function to run GridLAB-D model.
        """
        self.modelOutput = util.gld.runModel(modelPath=(self.outDir + '/'
                                                        + self.model),
                                             gldPath=self.gldPath)
        # If a model failed to run, print to the console.
        if self.modelOutput.returncode:
            print("FAILURE! Individual {}'s model gave non-zero returncode.".format(self.uid))
        
    def update(self, stoptime=None):
        """Function to update regulator tap operations and positions, and 
        capacitor switch operations and states. This function should be called
        after running a model (runModel), and before evaluating fitness
        (evalFitness)
        
        NOTE: This function does nothing if the individual's controlFlag is 0,
            since these updates occur before running a model.
            
        INPUTS:
            stoptime: Provide if you dont' want to use self.stoptime
        """
        # Do nothing is the controlFlag is 0
        if self.controlFlag == 0:
            return
        
        # Determine times
        if not stoptime:
            stoptime=self.stoptime
        
        # For other control schemes, we need to get the state change and state
        # information from the database.
        # Update the regulator tap change count.
        # NOTE: passing stoptime for both times to ensure we ONLY read the 
        # change count at the end - otherwise we might double count.
        self.tapChangeCount = self.dbObj.sumMatrix(table=self.regData['table'],
                                                   cols=self.regData['changeColumns'],
                                                   starttime=stoptime,
                                                   stoptime=stoptime)
        # Update the capacitor switch count
        self.capSwitchCount = self.dbObj.sumMatrix(table=self.capData['table'],
                                                   cols=self.capData['changeColumns'],
                                                   starttime=stoptime,
                                                   stoptime=stoptime)
        
        # The 'newState' properties of 'reg' and 'cap' need updated.
        self.reg = self.dbObj.updateStatus(inDict=self.reg, dictType='reg',
                                           table=self.regData['table'],
                                           phaseCols=self.regData['stateColumns'],
                                           t=stoptime)
        
        self.cap = self.dbObj.updateStatus(inDict=self.cap, dictType='cap',
                                           table=self.capData['table'],
                                           phaseCols=self.capData['stateColumns'],
                                           t=stoptime)
        
        # Update the regulator and capacitor chromosomes. Note that the counts
        # have already been updated, so set updateCount to False.
        self.genRegChrom(flag=4, updateCount=False)
        self.genCapChrom(flag=4, updateCount=False)
                            
    def evalFitness(self, costs, tCol='t', starttime=None, stoptime=None,
                    voltFlag=True):
        """Function to evaluate fitness of individual. This is essentially a
            wrapper to call util.gld.computeCosts
        
        TODO: Add more evaluators of fitness like power factor
        
        INPUTS:
            costs: dict with the following fields:
                energy: price of energy
                tapChange: cost changing regulator taps
                capSwitch: cost of switching a capacitor
                undervoltage: cost of under voltage violations.
                overvoltage: cost of overvoltage violations
            tCol: name of time column(s)
            starttime: starttime to evaluate fitness for. If None, uses
                self.starttime
            stoptime: stoptime "..." self.stoptime
            voltFlag: Flag for whether to compute voltage violations or not.
                This should be removed once the mysql group recorder is ready.
                This is here to accomodate pmaps/experiment.py
        """
        # Establish times if they aren't given explicitely
        if starttime is None:
            starttime = self.starttime
            
        if stoptime is None:
            stoptime = self.stoptime
            
        # Determine voltage violation information.
        # TODO: Remove this hack once we don't have to use files...
        if voltFlag:
            voltFilesDir=self.outDir
            voltFiles=self.voltFiles
        else:
            voltFilesDir=None
            voltFiles=None

        # Compute costs.
        self.costs = util.gld.computeCosts(dbObj=self.dbObj,
                                           swingData=self.swingData,
                                           costs=costs,
                                           starttime=starttime,
                                           stoptime=stoptime,
                                           tCol=tCol,
                                           tapChangeCount=self.tapChangeCount,
                                           capSwitchCount=self.capSwitchCount,
                                           voltFilesDir=voltFilesDir,
                                           voltFiles=voltFiles
                                            )
    
    def writeRunUpdateEval(self, strModel, inPath, outDir, costs):
        """Function to write and run model, update individual, and evaluate
        the individual's fitness.
        
        INPUTS:
            strModel: see writeModel()
            inPath: see writeModel()
            outDir: see writeModel()
            costs: costs for fitness evaluation. See evalFitness
        """
        # Write the model.
        self.writeModel(strModel=strModel, inPath=inPath, outDir=outDir)
        # Run the model.
        self.runModel()
        # Update tap/cap states and change counts if necessary.
        self.update()
        # Evaluate costs.
        self.evalFitness(costs=costs)
        
    def buildCleanupDict(self, truncateFlag=False):
        """Function to build dictionary to be passed to the 'cleanupQueue' of 
        the 'cleanup' method.
        """
        # Initialize list of tables to clean up.
        tables = [self.swingData['power']['table'],
                  self.swingData['energy']['table']]
        # If we're not in manual control, there are more tables to clean.
        if self.controlFlag:
            tables.append(self.capData['table'])
            tables.append(self.regData['table'])
            
        d = {'tables': tables,
             'files': list(self.voltFiles),
             'dir': self.outDir}
        # Add the model file to the file list.
        d['files'].append(self.model)
        
        # If we have a vvo player, add it to the list
        try:
            d['files'].append(self.vvoPlayer)
        except:
            pass
        
        # Set flag for table truncation (rather than deletion)
        d['truncateFlag'] = truncateFlag
        
        # Return.
        return d

def cleanup(cleanupQueue, dbObj):
    """Method to cleanup (delete) an individuals files, tables, etc. 
    
    As the genetic algorithm grows in sophistication, more output is 
    created. With so many files and tables floating around, it can
    simply take forever to clean things up. This function should be called
    before an individual is deleted.
    
    Note this function is specifically formatted to work with threads.
    
    INPUTS:
        cleanupQueue: queue which will have dictionaries inserted into it.
            Dictionaries should contain a list of tables in 'tables', a list
            of files in 'files', and a directory to find the files in 'dir'.
        dbObj: initialized util/db.db class object for managing database
            connections.
    """
    while True:
        # Extract inputs from the queue.
        inDict = cleanupQueue.get()
        
        # Check input.
        if inDict is None:
            # 'None' is the done signal.
            cleanupQueue.task_done()
            break
        
        # Drop or truncate all tables.
        if inDict['truncateFlag']:
            for t in inDict['tables']:
                dbObj.truncateTable(table=t)         
        else:
            for t in inDict['tables']:
                dbObj.dropTable(table=t)

        # Delete all files.
        for f in inDict['files']:
            try:
                os.remove(inDict['dir'] + '/' + f)
            except PermissionError:
                # We don't want a permission error spoiling a long run...
                # Note that all files should get overwritten by either this
                # program or GridLAB-D anyways...
                pass
            
        # Delete the directory if it's empty.
        try:
            os.rmdir(inDict['dir'])
        except:
            pass
        """
        c = os.listdir(inDict['dir'])
        
        if c:
            try:
                raise UserWarning(('The directory {} is not empty.\n'
                                   + 'It still contains {}'.format(inDict['dir'],
                                                                   c)))
            except UserWarning as w:
                print(type(w)) # the exception instance
                print(w.args) # arguments stored in .args
                print(w) # may be repetitive
                
        else:
            os.rmdir(inDict['dir'])
        """

        
        # Cleanup complete.
        cleanupQueue.task_done()
        