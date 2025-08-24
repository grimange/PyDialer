"""
Inbound Call Routing and Queuing System for PyDialer.

This module provides comprehensive inbound call routing, queue management,
and agent assignment functionality for the PyDialer call center system.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import deque
import uuid

from django.conf import settings
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class CallPriority(Enum):
    """Call priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    EMERGENCY = 5


class QueueStrategy(Enum):
    """Queue routing strategies."""
    FIFO = "fifo"  # First In, First Out
    LIFO = "lifo"  # Last In, First Out
    PRIORITY = "priority"  # Priority-based routing
    SKILLS = "skills"  # Skills-based routing
    ROUND_ROBIN = "round_robin"  # Round-robin agent assignment
    LEAST_OCCUPIED = "least_occupied"  # Route to least busy agent


class AgentStatus(Enum):
    """Agent availability status."""
    AVAILABLE = "available"
    BUSY = "busy"
    ON_CALL = "on_call"
    WRAP_UP = "wrap_up"
    BREAK = "break"
    OFFLINE = "offline"
    UNAVAILABLE = "unavailable"


@dataclass
class QueuedCall:
    """Represents a call waiting in queue."""
    call_id: str
    caller_id: str
    did_number: str
    priority: CallPriority = CallPriority.NORMAL
    queue_name: str = "default"
    skills_required: List[str] = field(default_factory=list)
    queue_time: datetime = field(default_factory=timezone.now)
    max_wait_time: Optional[int] = None  # seconds
    callback_number: Optional[str] = None
    customer_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.queue_time, str):
            self.queue_time = datetime.fromisoformat(self.queue_time)
    
    @property
    def wait_time(self) -> int:
        """Calculate current wait time in seconds."""
        return int((timezone.now() - self.queue_time).total_seconds())
    
    @property
    def is_expired(self) -> bool:
        """Check if call has exceeded maximum wait time."""
        if self.max_wait_time is None:
            return False
        return self.wait_time > self.max_wait_time


@dataclass
class Agent:
    """Represents an agent in the routing system."""
    agent_id: str
    username: str
    status: AgentStatus = AgentStatus.OFFLINE
    skills: Set[str] = field(default_factory=set)
    current_call_id: Optional[str] = None
    last_call_end: Optional[datetime] = None
    total_calls: int = 0
    queue_names: Set[str] = field(default_factory=lambda: {"default"})
    priority: int = 1  # Agent priority for routing
    max_concurrent_calls: int = 1
    
    @property
    def is_available(self) -> bool:
        """Check if agent is available to take calls."""
        return self.status == AgentStatus.AVAILABLE and not self.current_call_id
    
    @property
    def can_handle_skills(self, required_skills: List[str]) -> bool:
        """Check if agent has required skills."""
        return set(required_skills).issubset(self.skills) if required_skills else True


@dataclass
class Queue:
    """Represents a call queue."""
    name: str
    strategy: QueueStrategy = QueueStrategy.FIFO
    max_wait_time: int = 300  # 5 minutes default
    max_queue_size: int = 100
    announcement_file: Optional[str] = None
    music_on_hold: str = "default"
    periodic_announcement: Optional[str] = None
    announcement_frequency: int = 60  # seconds
    overflow_queue: Optional[str] = None
    priority_queue: bool = False
    skills_required: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        if isinstance(self.skills_required, list):
            self.skills_required = set(self.skills_required)


class CallRoutingEngine:
    """
    Inbound call routing and queuing engine.
    
    Manages call queues, agent assignment, and routing strategies
    for optimal call center operations.
    """
    
    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self.queues: Dict[str, Queue] = {}
        self.queued_calls: Dict[str, deque[QueuedCall]] = {}
        self.active_calls: Dict[str, QueuedCall] = {}
        
        # Routing statistics
        self.stats = {
            'total_routed': 0,
            'total_queued': 0,
            'total_abandoned': 0,
            'total_overflow': 0,
            'average_wait_time': 0.0
        }
        
        # Initialize default queue
        self._create_default_queue()
        
        # Background task for queue management
        self._queue_task: Optional[asyncio.Task] = None
        
        logger.info("Call routing engine initialized")
    
    def _create_default_queue(self) -> None:
        """Create the default call queue."""
        default_queue = Queue(
            name="default",
            strategy=QueueStrategy.FIFO,
            max_wait_time=300,
            max_queue_size=50,
            music_on_hold="default"
        )
        self.add_queue(default_queue)
    
    async def start(self) -> None:
        """Start the routing engine background tasks."""
        if self._queue_task is None or self._queue_task.done():
            self._queue_task = asyncio.create_task(self._queue_monitor_loop())
            logger.info("Call routing engine started")
    
    async def stop(self) -> None:
        """Stop the routing engine background tasks."""
        if self._queue_task and not self._queue_task.done():
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
            logger.info("Call routing engine stopped")
    
    def add_queue(self, queue: Queue) -> None:
        """Add a new call queue."""
        self.queues[queue.name] = queue
        if queue.name not in self.queued_calls:
            self.queued_calls[queue.name] = deque()
        logger.info(f"Added queue: {queue.name}")
    
    def remove_queue(self, queue_name: str) -> None:
        """Remove a call queue."""
        if queue_name == "default":
            raise ValueError("Cannot remove default queue")
        
        if queue_name in self.queues:
            # Move any queued calls to default queue
            if queue_name in self.queued_calls:
                while self.queued_calls[queue_name]:
                    call = self.queued_calls[queue_name].popleft()
                    call.queue_name = "default"
                    self.queued_calls["default"].append(call)
                del self.queued_calls[queue_name]
            
            del self.queues[queue_name]
            logger.info(f"Removed queue: {queue_name}")
    
    def add_agent(self, agent: Agent) -> None:
        """Add an agent to the routing system."""
        self.agents[agent.agent_id] = agent
        logger.info(f"Added agent: {agent.agent_id} ({agent.username})")
    
    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from the routing system."""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            # Handle any active call
            if agent.current_call_id:
                logger.warning(f"Removing agent {agent_id} with active call {agent.current_call_id}")
            del self.agents[agent_id]
            logger.info(f"Removed agent: {agent_id}")
    
    def update_agent_status(self, agent_id: str, status: AgentStatus) -> None:
        """Update agent status."""
        if agent_id in self.agents:
            old_status = self.agents[agent_id].status
            self.agents[agent_id].status = status
            logger.info(f"Agent {agent_id} status changed: {old_status.value} -> {status.value}")
            
            # Trigger routing check if agent became available
            if status == AgentStatus.AVAILABLE:
                asyncio.create_task(self._process_queue_routing())
    
    async def route_inbound_call(
        self,
        call_id: str,
        caller_id: str,
        did_number: str,
        queue_name: str = "default",
        priority: CallPriority = CallPriority.NORMAL,
        skills_required: List[str] = None,
        customer_data: Dict[str, Any] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Route an inbound call to an available agent or queue.
        
        Returns:
            Tuple of (routed_to_agent, agent_id_or_queue_message)
        """
        skills_required = skills_required or []
        customer_data = customer_data or {}
        
        # Validate queue exists
        if queue_name not in self.queues:
            logger.error(f"Queue {queue_name} not found for call {call_id}")
            queue_name = "default"
        
        queue = self.queues[queue_name]
        
        # Create queued call object
        queued_call = QueuedCall(
            call_id=call_id,
            caller_id=caller_id,
            did_number=did_number,
            priority=priority,
            queue_name=queue_name,
            skills_required=skills_required,
            max_wait_time=queue.max_wait_time,
            customer_data=customer_data
        )
        
        # Try immediate routing to available agent
        agent = await self._find_available_agent(queue_name, skills_required)
        if agent:
            success = await self._assign_call_to_agent(queued_call, agent)
            if success:
                self.stats['total_routed'] += 1
                return True, agent.agent_id
        
        # No available agent, add to queue
        return await self._add_to_queue(queued_call)
    
    async def _find_available_agent(
        self,
        queue_name: str,
        skills_required: List[str] = None
    ) -> Optional[Agent]:
        """Find an available agent for the queue with required skills."""
        available_agents = [
            agent for agent in self.agents.values()
            if (agent.is_available and
                queue_name in agent.queue_names and
                agent.can_handle_skills(skills_required))
        ]
        
        if not available_agents:
            return None
        
        queue = self.queues[queue_name]
        
        # Apply routing strategy
        if queue.strategy == QueueStrategy.ROUND_ROBIN:
            # Find agent who has been idle longest
            return min(available_agents, key=lambda a: a.last_call_end or datetime.min)
        
        elif queue.strategy == QueueStrategy.LEAST_OCCUPIED:
            # Find agent with fewest total calls
            return min(available_agents, key=lambda a: a.total_calls)
        
        elif queue.strategy == QueueStrategy.PRIORITY:
            # Find highest priority agent
            return max(available_agents, key=lambda a: a.priority)
        
        else:  # FIFO or default
            # Return first available agent
            return available_agents[0]
    
    async def _assign_call_to_agent(self, call: QueuedCall, agent: Agent) -> bool:
        """Assign a call to an agent."""
        try:
            # Update agent status
            agent.status = AgentStatus.ON_CALL
            agent.current_call_id = call.call_id
            agent.total_calls += 1
            
            # Store active call
            self.active_calls[call.call_id] = call
            
            # Notify agent via WebSocket
            await self._notify_agent_call_assignment(agent, call)
            
            logger.info(f"Assigned call {call.call_id} to agent {agent.agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error assigning call {call.call_id} to agent {agent.agent_id}: {e}")
            # Revert agent status
            agent.status = AgentStatus.AVAILABLE
            agent.current_call_id = None
            agent.total_calls -= 1
            return False
    
    async def _add_to_queue(self, call: QueuedCall) -> Tuple[bool, str]:
        """Add a call to the appropriate queue."""
        queue = self.queues[call.queue_name]
        call_queue = self.queued_calls[call.queue_name]
        
        # Check queue capacity
        if len(call_queue) >= queue.max_queue_size:
            # Handle overflow
            if queue.overflow_queue and queue.overflow_queue in self.queues:
                call.queue_name = queue.overflow_queue
                return await self._add_to_queue(call)
            else:
                self.stats['total_overflow'] += 1
                logger.warning(f"Queue {call.queue_name} full, rejecting call {call.call_id}")
                return False, "Queue full"
        
        # Add to queue based on priority
        if queue.priority_queue:
            # Insert based on priority
            inserted = False
            for i, queued_call in enumerate(call_queue):
                if call.priority.value > queued_call.priority.value:
                    call_queue.insert(i, call)
                    inserted = True
                    break
            if not inserted:
                call_queue.append(call)
        else:
            # Simple FIFO/LIFO
            if queue.strategy == QueueStrategy.LIFO:
                call_queue.appendleft(call)
            else:
                call_queue.append(call)
        
        self.stats['total_queued'] += 1
        
        # Notify caller about queue position
        position = self._get_queue_position(call)
        await self._notify_caller_queued(call, position)
        
        logger.info(f"Added call {call.call_id} to queue {call.queue_name} at position {position}")
        return False, f"Queued at position {position}"
    
    def _get_queue_position(self, call: QueuedCall) -> int:
        """Get the position of a call in its queue."""
        call_queue = self.queued_calls[call.queue_name]
        for i, queued_call in enumerate(call_queue):
            if queued_call.call_id == call.call_id:
                return i + 1
        return 0
    
    async def _process_queue_routing(self) -> None:
        """Process all queues and attempt to route waiting calls."""
        for queue_name, call_queue in self.queued_calls.items():
            if not call_queue:
                continue
            
            # Process calls in queue order
            calls_to_remove = []
            for call in list(call_queue):
                # Check if call expired
                if call.is_expired:
                    calls_to_remove.append(call)
                    self.stats['total_abandoned'] += 1
                    await self._handle_abandoned_call(call)
                    continue
                
                # Try to find agent
                agent = await self._find_available_agent(
                    queue_name, 
                    call.skills_required
                )
                if agent:
                    success = await self._assign_call_to_agent(call, agent)
                    if success:
                        calls_to_remove.append(call)
                        self.stats['total_routed'] += 1
                        # Update wait time stats
                        self._update_wait_time_stats(call.wait_time)
            
            # Remove processed calls from queue
            for call in calls_to_remove:
                try:
                    call_queue.remove(call)
                except ValueError:
                    pass  # Call already removed
    
    async def _queue_monitor_loop(self) -> None:
        """Background loop to monitor queues and process routing."""
        try:
            while True:
                await self._process_queue_routing()
                await self._send_queue_stats()
                await asyncio.sleep(5)  # Check every 5 seconds
        except asyncio.CancelledError:
            logger.info("Queue monitor loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in queue monitor loop: {e}")
            await asyncio.sleep(10)  # Wait before retrying
    
    async def call_completed(self, call_id: str, agent_id: str) -> None:
        """Handle call completion."""
        if call_id in self.active_calls:
            del self.active_calls[call_id]
        
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.current_call_id = None
            agent.last_call_end = timezone.now()
            agent.status = AgentStatus.WRAP_UP
            
            # Auto-transition to available after wrap-up time
            wrap_up_time = getattr(settings, 'AGENT_WRAPUP_TIME', 30)
            asyncio.create_task(self._auto_available_after_wrapup(agent_id, wrap_up_time))
        
        logger.info(f"Call {call_id} completed by agent {agent_id}")
    
    async def _auto_available_after_wrapup(self, agent_id: str, delay: int) -> None:
        """Auto-set agent to available after wrap-up time."""
        await asyncio.sleep(delay)
        if agent_id in self.agents and self.agents[agent_id].status == AgentStatus.WRAP_UP:
            self.agents[agent_id].status = AgentStatus.AVAILABLE
            logger.info(f"Agent {agent_id} automatically set to available after wrap-up")
    
    async def _notify_agent_call_assignment(self, agent: Agent, call: QueuedCall) -> None:
        """Notify agent of call assignment via WebSocket."""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                await channel_layer.group_send(
                    f"agent_{agent.agent_id}",
                    {
                        'type': 'call_assignment',
                        'call_id': call.call_id,
                        'caller_id': call.caller_id,
                        'did_number': call.did_number,
                        'queue_name': call.queue_name,
                        'wait_time': call.wait_time,
                        'customer_data': call.customer_data
                    }
                )
        except Exception as e:
            logger.error(f"Error notifying agent {agent.agent_id}: {e}")
    
    async def _notify_caller_queued(self, call: QueuedCall, position: int) -> None:
        """Notify caller about queue status."""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                await channel_layer.group_send(
                    f"call_{call.call_id}",
                    {
                        'type': 'queue_status',
                        'position': position,
                        'estimated_wait': self._estimate_wait_time(call.queue_name),
                        'queue_name': call.queue_name
                    }
                )
        except Exception as e:
            logger.error(f"Error notifying caller for call {call.call_id}: {e}")
    
    async def _handle_abandoned_call(self, call: QueuedCall) -> None:
        """Handle an abandoned call that exceeded max wait time."""
        logger.info(f"Call {call.call_id} abandoned after {call.wait_time} seconds")
        
        # Remove from queue
        if call.queue_name in self.queued_calls:
            try:
                self.queued_calls[call.queue_name].remove(call)
            except ValueError:
                pass
        
        # Notify via WebSocket
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                await channel_layer.group_send(
                    f"call_{call.call_id}",
                    {
                        'type': 'call_abandoned',
                        'reason': 'max_wait_time_exceeded',
                        'wait_time': call.wait_time
                    }
                )
        except Exception as e:
            logger.error(f"Error notifying about abandoned call {call.call_id}: {e}")
    
    def _estimate_wait_time(self, queue_name: str) -> int:
        """Estimate wait time for a queue based on current conditions."""
        if queue_name not in self.queued_calls:
            return 0
        
        queue_size = len(self.queued_calls[queue_name])
        available_agents = sum(
            1 for agent in self.agents.values()
            if agent.is_available and queue_name in agent.queue_names
        )
        
        if available_agents == 0:
            return queue_size * 120  # Assume 2 minutes per call if no agents
        
        avg_call_time = 180  # 3 minutes average call time
        return int((queue_size / available_agents) * avg_call_time)
    
    def _update_wait_time_stats(self, wait_time: int) -> None:
        """Update average wait time statistics."""
        current_avg = self.stats['average_wait_time']
        total_routed = self.stats['total_routed']
        
        if total_routed == 0:
            self.stats['average_wait_time'] = wait_time
        else:
            # Calculate running average
            self.stats['average_wait_time'] = (
                (current_avg * (total_routed - 1) + wait_time) / total_routed
            )
    
    async def _send_queue_stats(self) -> None:
        """Send queue statistics via WebSocket."""
        try:
            stats_data = {
                'type': 'queue_stats',
                'queues': {},
                'agents': {},
                'overall_stats': self.stats
            }
            
            # Queue statistics
            for queue_name, queue in self.queues.items():
                call_queue = self.queued_calls.get(queue_name, deque())
                stats_data['queues'][queue_name] = {
                    'name': queue_name,
                    'calls_waiting': len(call_queue),
                    'longest_wait': max([call.wait_time for call in call_queue], default=0),
                    'strategy': queue.strategy.value
                }
            
            # Agent statistics
            for agent_id, agent in self.agents.items():
                stats_data['agents'][agent_id] = {
                    'agent_id': agent_id,
                    'username': agent.username,
                    'status': agent.status.value,
                    'total_calls': agent.total_calls,
                    'current_call': agent.current_call_id
                }
            
            channel_layer = get_channel_layer()
            if channel_layer:
                await channel_layer.group_send("supervisors", stats_data)
                
        except Exception as e:
            logger.error(f"Error sending queue stats: {e}")
    
    def get_queue_stats(self, queue_name: str = None) -> Dict[str, Any]:
        """Get statistics for a specific queue or all queues."""
        if queue_name:
            if queue_name not in self.queues:
                return {}
            
            call_queue = self.queued_calls.get(queue_name, deque())
            return {
                'name': queue_name,
                'calls_waiting': len(call_queue),
                'longest_wait': max([call.wait_time for call in call_queue], default=0),
                'available_agents': sum(
                    1 for agent in self.agents.values()
                    if agent.is_available and queue_name in agent.queue_names
                ),
                'strategy': self.queues[queue_name].strategy.value
            }
        else:
            # Return stats for all queues
            stats = {}
            for qname in self.queues.keys():
                stats[qname] = self.get_queue_stats(qname)
            return stats


# Global routing engine instance
_routing_engine: Optional[CallRoutingEngine] = None


async def get_routing_engine() -> CallRoutingEngine:
    """Get or create global routing engine instance."""
    global _routing_engine
    if _routing_engine is None:
        _routing_engine = CallRoutingEngine()
        await _routing_engine.start()
    return _routing_engine


async def cleanup_routing_engine() -> None:
    """Clean up global routing engine instance."""
    global _routing_engine
    if _routing_engine:
        await _routing_engine.stop()
        _routing_engine = None
