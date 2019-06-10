/*******************************************************************************
 * Copyright (c) 2017, Battelle Memorial Institute All rights reserved.
 * Battelle Memorial Institute (hereinafter Battelle) hereby grants permission to any person or entity 
 * lawfully obtaining a copy of this software and associated documentation files (hereinafter the 
 * Software) to redistribute and use the Software in source and binary forms, with or without modification. 
 * Such person or entity may use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of 
 * the Software, and may permit others to do so, subject to the following conditions:
 * Redistributions of source code must retain the above copyright notice, this list of conditions and the 
 * following disclaimers.
 * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and 
 * the following disclaimer in the documentation and/or other materials provided with the distribution.
 * Other than as used herein, neither the name Battelle Memorial Institute or Battelle may be used in any 
 * form whatsoever without the express written consent of Battelle.
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY 
 * EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF 
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL 
 * BATTELLE OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, 
 * OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE 
 * GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED 
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING 
 * NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED 
 * OF THE POSSIBILITY OF SUCH DAMAGE.
 * General disclaimer for use with OSS licenses
 * 
 * This material was prepared as an account of work sponsored by an agency of the United States Government. 
 * Neither the United States Government nor the United States Department of Energy, nor Battelle, nor any 
 * of their employees, nor any jurisdiction or organization that has cooperated in the development of these 
 * materials, makes any warranty, express or implied, or assumes any legal liability or responsibility for 
 * the accuracy, completeness, or usefulness or any information, apparatus, product, software, or process 
 * disclosed, or represents that its use would not infringe privately owned rights.
 * 
 * Reference herein to any specific commercial product, process, or service by trade name, trademark, manufacturer, 
 * or otherwise does not necessarily constitute or imply its endorsement, recommendation, or favoring by the United 
 * States Government or any agency thereof, or Battelle Memorial Institute. The views and opinions of authors expressed 
 * herein do not necessarily state or reflect those of the United States Government or any agency thereof.
 * 
 * PACIFIC NORTHWEST NATIONAL LABORATORY operated by BATTELLE for the 
 * UNITED STATES DEPARTMENT OF ENERGY under Contract DE-AC05-76RL01830
 ******************************************************************************/
package gov.pnnl.goss.gridappsd.api;

import gov.pnnl.goss.gridappsd.dto.SimulationContext;
import gov.pnnl.goss.gridappsd.dto.TestConfig;
import gov.pnnl.goss.gridappsd.dto.events.Event;

import java.util.List;

import javax.jms.Destination;

import com.google.gson.JsonObject;

public interface TestManager {
	
	
	/**
	 * This method receives test request from ProcessManager, checks request 
	 * parameters and forwards them to be processed to specific methods.
	 * other specific methods.
	 * 
	 * @param testConfig
	 *            Configuration containing test request.
	 * @param simulationContext
	 *            Context information of currently running simulation.
	 * @param rulePort
	 *            A unique port number generated by ProcessMananger for rule
	 *            engine if testConfig contains rules other wise defaults to 0.
	 */
	public void handleTestRequest(TestConfig testConfig, SimulationContext simulationContext);
	
	/**
	 * This method injects Events in a currently running simulation. 
	 * @param events List of Event objects
	 * @param simulationId Id of currently running simulation
	 * @return 
	 */
	public List<Event> sendEventsToSimulation(List<Event> events, String simulationId);
	
	/**
	 * This method compares output from the currently running simulation with 
	 * output from an older simulation. It publishes the comparison results on
	 * the topic defined under GridappsdConstants's topic_simulationTestOutput
	 * variable.
	 * @param testConfig 
	 * @param simulationIdOne simulation id of currently running simulation
	 * @param simulationIdTwo Simulation id of older simulation
	 */
	public void compareSimulations(String simulationIdOne, String simulationIdTwo);
	
	/**
	 * This method compares simulation output with provided expected simulation
	 * output.
	 * @param simulationId Id of the surrently running simulation
	 * @param expectedResults Expected simulation output 
	 */
	public void compareWithExpectedSimOutput(String simulationId, JsonObject expectedResults);
	
	/**
	 * This method update property of existing events for the simulation if the events 
	 * are not initiated yet.
	 * @param events List of events to be updated
	 * @param simulationId Id of the currently running simulation 
	 */
	public void updateEventForSimulation(List<Event> events, String simulationId);

	/**
	 * This method published status of events for the simulationId
	 * @param simulationId Id of currently running simulation
	 * @param replyDestination reply queue for the status
	 */
	public void sendEventStatus(String simulationId, Destination replyDestination);
	
}
