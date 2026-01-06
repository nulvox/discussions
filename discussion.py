#!/usr/bin/env python3
import yaml
import random
import os
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def create_agent(agent_config):
    model_config = agent_config['model']
    platform_map = {
        'ollama': ModelPlatformType.OLLAMA,
        'anthropic': ModelPlatformType.ANTHROPIC,
        'openai': ModelPlatformType.OPENAI,
    }
    
    platform = platform_map[model_config['platform']]
    model_kwargs = {'model_platform': platform, 'model_type': model_config['type']}
    
    if 'url' in model_config:
        model_kwargs['url'] = model_config['url']
    
    if 'api_key_env' in model_config:
        api_key = os.getenv(model_config['api_key_env'])
        if api_key:
            model_kwargs['api_key'] = api_key
    
    model = ModelFactory.create(**model_kwargs)
    
    return {
        'name': agent_config['name'],
        'agent': ChatAgent(
            system_message=agent_config['system_message'],
            model=model
        )
    }

def should_participate(agent_data, messages):
    """Ask agent if they want to participate this round"""
    decision_prompt = BaseMessage.make_user_message(
        role_name="Moderator",
        content="Given the discussion so far, do you have more to contribute? Reply only YES or NO."
    )
    
    try:
        response = agent_data['agent'].step(decision_prompt)
        response_text = response.msg.content.lower().strip()
        # Check for affirmative responses
        return any(word in response_text for word in ['yes', 'continue', 'speak', 'participate'])
    except Exception as e:
        print(f"Error getting participation decision from {agent_data['name']}: {e}")
        # Default to participating if there's an error
        return True

def run_discussion(config_path='/app/configs/discussion.yml'):
    config = load_config(config_path)
    
    # Create all agents
    agents = [create_agent(agent_config) for agent_config in config['agents']]
    
    # Initialize conversation
    topic = config['topic']
    max_turns = config.get('max_turns', 10)
    mode = config.get('mode', 'sequential')
    solo_speaker_limit = config.get('solo_speaker_rounds_limit', 2)
    
    initial_message = BaseMessage.make_user_message(
        role_name="Moderator",
        content=f"Discuss: {topic}"
    )
    
    messages = [initial_message]
    print(f"\n{'='*80}")
    print(f"Topic: {topic}")
    print(f"Mode: {mode}")
    print(f"Max turns: {'Unlimited' if max_turns == 0 else max_turns}")
    print(f"Participants: {', '.join([a['name'] for a in agents])}")
    print(f"{'='*80}\n")
    
    last_speaker_idx = None
    solo_rounds = 0
    last_solo_speaker = None
    turn = 0
    
    while True:
        turn += 1
        
        # Check turn limit (0 means unlimited)
        if max_turns > 0 and turn > max_turns:
            print("\n--- Maximum turns reached ---\n")
            break
        
        print(f"\n--- Turn {turn} ---\n")
        
        # Natural mode: ask agents if they want to participate
        if mode == 'natural':
            print("Checking participation...\n")
            participants = []
            for agent_data in agents:
                wants_to_speak = should_participate(agent_data, messages)
                if wants_to_speak:
                    participants.append(agent_data)
                    print(f"  {agent_data['name']}: will speak")
                else:
                    print(f"  {agent_data['name']}: passing")
            
            print()
            
            # Check termination conditions
            if len(participants) == 0:
                print("Discussion concluded - no agents wish to continue\n")
                break
            
            # Check if same solo speaker for multiple rounds
            if len(participants) == 1:
                current_solo = participants[0]['name']
                if last_solo_speaker == current_solo:
                    solo_rounds += 1
                    if solo_rounds >= solo_speaker_limit:
                        print(f"Discussion concluded - only {current_solo} participated for {solo_speaker_limit} consecutive rounds\n")
                        break
                else:
                    solo_rounds = 1
                    last_solo_speaker = current_solo
            else:
                solo_rounds = 0
                last_solo_speaker = None
            
            agent_order = participants
        
        # Sequential mode: agents in config order
        elif mode == 'sequential':
            agent_order = agents
        
        # Random mode: randomized order, prevent consecutive same speaker
        else:  # random mode
            agent_order = agents.copy()
            random.shuffle(agent_order)
        
        # Have agents speak
        for agent_data in agent_order:
            # In random mode, prevent same agent speaking twice in a row
            if mode == 'random' and last_speaker_idx is not None:
                current_idx = agents.index(agent_data)
                if current_idx == last_speaker_idx:
                    continue
            
            response = agent_data['agent'].step(messages[-1])
            messages.append(response.msg)
            
            print(f"{agent_data['name']}:")
            print(f"{response.msg.content}\n")
            
            last_speaker_idx = agents.index(agent_data)
    
    print(f"{'='*80}")
    print(f"Discussion ended after {turn} turns")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    run_discussion()