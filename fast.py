
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union
import openai
import json
import uuid
import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from chat_db import chat_db

# Import models from models.py
from models import (
    Condition, ConditionGroup, Connector, Operator, 
    RulesPayload, RuleRequest, RuleResponse
)

load_dotenv()

# RUN THIS APP
# uvicorn multi-msg:app --reload
app = FastAPI(title="Mortgage Rule Generator API", version="1.0.0")

# ---------- External API Configuration ----------
EXTERNAL_API_BASE_URL = "https://lmsdev-external-distributor-api.pulseid.com"
API_KEY = "03111dadd30c310c344a007c2a3ad4999c1de2d4974b432928a7591766842b64f615dacc2af4cab1710305e9cdb3a4179bde3588cffa879719aa26b707e6f21e"
API_SECRET = "55347a2fa1bbac0a40e08275f39d451ef607ef086bedae2cacace8f57b4a82fa899cf701ff2f0848fd96fa08f2264f0d9f98513854d91077e14dee101d8bdd5f"
DEFAULT_CLIENT_ID = 307

# Initialize OpenAI client
try:
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    raise RuntimeError(f"Failed to initialize OpenAI client: {str(e)}")

# Define CSV file structures with exact column names (fallback)
CSV_STRUCTURES = {
    "sample_mortgage_accounts.csv": [
        "customer_id", "product_type", "account_status", "loan_open_date", "loan_balance"
    ],
    "sample_loan_repayments.csv": [
        "repayment_id", "customer_id", "loan_account_number", "repayment_date",
        "repayment_amount", "installment_number", "payment_method_status", "loan_type",
        "interest_component", "principal_component", "remaining_balance"
    ],
    "sample_telco_billing.csv": [
        "billing_id", "customer_id", "bill_date", "bill_amount", "plan_type",
        "data_used_gb", "voice_minutes", "sms_count", "channel"
    ],
    "sample_product_enrollments.csv": [
        "enrollment_id", "customer_id", "product_type", "product_name", "enrollment_date", "status"
    ],
    "sample_customer_profiles.csv": [
        "customer_id", "name", "email", "phone", "dob", "gender",
        "region", "segment", "household_id", "is_primary"
    ],
    "sample_savings_account_transactions.csv": [
        "transaction_id", "account_id", "customer_id", "amount", "date", "transaction_type"
    ],
    "sample_credit_card_transactions.csv": [
        "customer_id", "card_number", "transaction_date", "transaction_amount", "transaction_type"
    ]
}

# ---------- External API Functions ----------

def convert_static_to_rich_format(static_data: Dict[str, List[str]]) -> Dict[str, List[Dict[str, str]]]:
    """Convert static CSV_STRUCTURES format to rich format with metadata."""
    rich_format = {}
    for source_name, fields in static_data.items():
        rich_fields = []
        for i, field in enumerate(fields):
            rich_fields.append({
                "field": field,
                "field_id": f"static_{i}",  # Generate static field ID
                "type": "string",  # Default type for static data
                "description": f"{field} field from {source_name}",
                "data_source_id": f"static_{source_name}"  # Add static data source ID
            })
        rich_format[source_name] = rich_fields
    return rich_format

def fetch_data_sources(client_id: int = DEFAULT_CLIENT_ID) -> Dict[str, List[Dict[str, str]]]:
    try:
        headers = {
            "x-api-key": API_KEY,
            "x-api-secret": API_SECRET
        }
        
        params = {
            "clientId": client_id,
            "page": 1,
            "limit": 10,
            "status": "exact:ACTIVE"
        }
        
        response = requests.get(
            f"{EXTERNAL_API_BASE_URL}/data-sources",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"API request failed with status {response.status_code}: {response.text}")
            return convert_static_to_rich_format(CSV_STRUCTURES)  # Fallback to static data
            
        data = response.json()

        if not data.get("success"):
            print(f"API returned error: {data}")
            return convert_static_to_rich_format(CSV_STRUCTURES)  # Fallback to static data
            
        # Extract data sources and their mapping columns with rich metadata
        sources_mapping = {}
        
        for source in data.get("data", []):
            source_name = source.get("sourceName")
            source_id = source.get("id") # Get the data source ID
            mapping_data = source.get("mapping", {}).get("mappingData", {})
            mapping_list = mapping_data.get("mapping", [])
            
            if source_name and mapping_list:
                fields = []
                for mapping_item in mapping_list:
                    mapped_field = mapping_item.get("mappedField")
                    field_id = mapping_item.get("id")  # Extract field ID
                    field_type = mapping_item.get("mappingType", "string")
                    field_description = mapping_item.get("description", "")
                    
                    if mapped_field:
                        fields.append({
                            "field": mapped_field,
                            "field_id": field_id,  # Include field ID
                            "type": field_type,
                            "description": field_description or f"{mapped_field} field",
                            "data_source_id": source_id # Add data source ID
                        })
                
                if fields:
                    sources_mapping[source_name] = fields
        
        print("sources_mapping", sources_mapping)
        # Return static data if no dynamic data found (convert to new format)
        if not sources_mapping:
            return convert_static_to_rich_format(CSV_STRUCTURES)
        
        return sources_mapping
        
    except Exception as e:
        print(f"Error fetching data sources: {e}")
        return convert_static_to_rich_format(CSV_STRUCTURES)  # Fallback to static data

def detect_response_type(parsed_json: Dict[str, Any]) -> str:
    """Detect the type of response from the parsed JSON"""
    if "rules" in parsed_json:
        return "rule"
    elif "logical_structure" in parsed_json and "user_message" in parsed_json:
        return "confirmation"
    elif "message" in parsed_json and len(parsed_json) == 1:
        return "general"
    elif "data_sources_info" in parsed_json:
        return "data_sources"
    else:
        return "unknown"

def create_field_mapping(data_sources: Dict[str, List[Dict[str, str]]]) -> Dict[str, str]:
    """Create a mapping from field name to field ID across all data sources."""
    field_mapping = {}
    for source_name, fields in data_sources.items():
        for field_info in fields:
            field_name = field_info["field"]
            field_id = field_info["field_id"]
            field_mapping[field_name] = field_id
    return field_mapping

async def generate_rule_with_openai_complex(user_input: str, client_id: Optional[int] = None) -> Dict[str, Any]:
    """Generate rules using OpenAI with enhanced chat flow and data source explanations"""
    # Fetch dynamic data sources or fallback to static
    data_sources = fetch_data_sources(client_id or DEFAULT_CLIENT_ID)
    
    # Create field name to field ID mapping
    field_mapping = create_field_mapping(data_sources)
    
    # Format available data with rich metadata for better AI context
    available_data_lines = []
    for source_name, fields in data_sources.items():
        # Get data source ID from first field (all fields in a source have same data_source_id)
        data_source_id = fields[0].get("data_source_id", "N/A") if fields else "N/A"
        available_data_lines.append(f"- {source_name} (ID: {data_source_id}):")
        for field_info in fields:
            field_name = field_info["field"]
            field_id = field_info["field_id"]
            field_type = field_info["type"]
            field_desc = field_info["description"]
            available_data_lines.append(f"  * {field_name} (ID: {field_id}, {field_type}): {field_desc}")
    
    available_data = "\n".join(available_data_lines)
    
    # Create field mapping string for the prompt
    field_mapping_lines = []
    for field_name, field_id in field_mapping.items():
        field_mapping_lines.append(f"  * {field_name} -> {field_id}")
    field_mapping_str = "\n".join(field_mapping_lines)

    # Enhanced system prompt with professional yet friendly tone
    # Enhanced system prompt with professional yet friendly tone
    system_prompt = f"""
# Role Definition
You are a helpful, professional, and friendly rule generation assistant for financial services. Your primary goal is to help users create accurate business rules through natural conversation.

# Behavior Guidelines
1. Communication Style:
   - Be polite, patient, and professional
   - Use clear, simple language (avoid jargon unless necessary)
   - Maintain a helpful and approachable tone
   - Confirm understanding before proceeding
   - Provide explanations when asked

2. Core Responsibilities:
   - Rule Generation:
     * Understand user requirements
     * Propose all posible logical structures and ask for Which Option would be match perfectly. as Option 1, Option 2, Option 3..
     * Generate rules based on user's selected logical structure
     * Confirm understanding before generating rules
     * Handle corrections gracefully
   - Data Source Information:
     * Explain available data sources
     * Describe fields and their meanings
     * Suggest relevant fields for rules

# Response Templates
1. Initial Greeting (when no history exists):
{{
    "message": "Hello! I'm your rule assistant. I can help create business rules using our data. What would you like to achieve today?"
}}

2. Rule Confirmation:
{{
    "message": "Here's how I understand your requirement...",
    "logical_structure": "(Condition A) AND (Condition B OR Condition C)",
    "user_message": "Does this match your needs? If not, please explain what should change."
}}

3. Data Source Explanation:
{{
    "data_sources_info": {{
        "source_name": "sample_credit_card_transactions",
        "fields": [
            {{
                "field": "transaction_amount",
                "description": "The dollar amount of the transaction",
                "type": "decimal"
            }},
            {{
                "field": "transaction_type",
                "description": "Type of transaction (purchase, refund etc)",
                "type": "string"
            }}
        ]
    }}
}}

4. General Messages:
{{
    "message": "I can help with that. First, could you clarify..."
}}

5. Final Rule Output Structure:
{{
    "rules": [
        {{
            "id": <id>,
            "dataSource": <data source name>,
            "dataSourceId": <data source id>,
            "field": <field name>,
            "fieldId": <field id>,
            "eligibilityPeriod": "Rolling 30 days",
            "function": <function>,
            "operator": <operator>,
            "value": "2500",
            "priority": null,
            "ruleType": "condition",
            "connector": "AND"
        }},
        {{
            "id": <id>,
            "priority": null,
            "ruleType": "conditionGroup",
            "conditions": [
                {{
                    "id": <id>,
                    "dataSource": <data source name>,
                    "dataSourceId": <data source id>,
                    "field": <field name>,
                    "fieldId": <field id>,
                    "eligibilityPeriod": "n_a",
                    "function": "n_a",
                    "operator": <operator>,
                    "value": "active",
                    "connector": "OR"
                }},
                {{
                    "id": <id>,
                    "dataSource": <data source name>,
                    "dataSourceId": <data source id>,
                    "field": <field name>,
                    "fieldId": <field id>,
                    "eligibilityPeriod": "n_a",
                    "function": "n_a",
                    "operator": <operator>,
                    "value": "1000"
                }}
            ]
        }}
    ]
}}

# Technical Specifications
## Data Handling Requirements:
1. Use ONLY the exact column names from provided data sources
2. Use the exact fieldId from the field mapping for each field
3. Use the exact dataSourceId from the available data sources
4. For time references like "last month", use "Rolling 30 days"
5. For amount aggregations, use "sum" function

## Operator Specifications (use value only):
{{
    "equal": "=",
    "not_equal": "≠",
    "greater_than": ">",
    "less_than": "<",
    "greater_than_or_equal": "≥",
    "less_than_or_equal": "≤",
    "between": "Between",
    "not_between": "Not Between",
    "contains": "Contains",
    "begins_with": "Begins With",
    "ends_with": "Ends With",
    "does_not_contain": "Does Not Contain"
}}

## Function Specifications (use value only):
{{
    "n_a": "N/A",
    "sum": "Sum",
    "count": "Count",
    "average": "Average",
    "max": "Maximum",
    "min": "Minimum",
    "exact_match": "Exact Match",
    "change_detected": "Change Detected",
    "exists": "Exists",
    "consecutive": "Consecutive",
    "streak_count": "Streak Count",
    "first_time": "First Time",
    "nth_time": "Nth Time",
    "recent_change": "Recent Change"
}}

# Logical Structure Examples
Input: "A and B or C"
Possible Outputs:
1. (A AND B) OR C
2. A AND (B OR C)
3. A AND B OR C

Example Case:
User input: "User spends over $2500 on a credit card in a month OR has an active mortgage AND loan balance is more than $1000"

Logical structures:
1. (User spends over $2500 on a credit card in a month) OR (has an active mortgage AND loan balance is more than $1000)
2. User spends over $2500 on a credit card in a month OR (has an active mortgage AND loan balance is more than $1000)

# Available Data Sources:
{available_data}

# Field Mapping:
{field_mapping_str}

# Critical Instructions
1. Strictly use only the specified operators and functions (values, not labels)
2. Follow the logical structure exactly as provided
3. Always confirm understanding before generating rules
4. For complex rules, break them down and verify each part
5. When asked about data, provide clear descriptions
6. If unsure, ask clarifying questions
7. Maintain professional yet friendly tone
8. Use natural conversation flow, not rigid Q&A

# Output Format
Respond ONLY with the JSON output as specified in the templates.
"""
    try:
        # Build messages array starting with system prompt
        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]
        
        # Add chat history if client_id is provided
        if client_id:
            try:
                chat_history = chat_db.get_chat_history(client_id)
                if chat_history and chat_history.get("chat_messages"):
                    # Add previous messages (excluding the current user input if it exists)
                    for msg in chat_history["chat_messages"]:
                        if msg["role"] in ["user", "assistant"]:
                            messages.append({
                                "role": msg["role"],
                                "content": msg["content"]
                            })
            except Exception as e:
                print(f"Warning: Failed to retrieve chat history: {e}")
        
        # Check if this is the first message and no history exists
        if len(messages) == 1:
            # Add a friendly greeting to start the conversation
            messages.append({
                "role": "assistant",
                "content": "Hello! I'm your rule generation assistant. How can I help you create business rules today?"
            })
            # Add current user input if it exists
            if user_input.strip():
                messages.append({
                    "role": "user",
                    "content": user_input
                })
        else:
            # Add current user input if it exists
            if user_input.strip():
                messages.append({
                    "role": "user",
                    "content": user_input
                })
        
        print(f"Sending {len(messages)} messages to OpenAI (including system prompt)")
        
        response = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=messages,
            temperature=0.5,
            response_format={"type": "json_object"}
        )
        
        response_content = response.choices[0].message.content

        # get JSON from response_content
        json_str = response_content[response_content.find('{'):response_content.rfind('}')+1]
        json_response = json.loads(json_str)
        
        # Post-process to add fieldId if missing
        if "rules" in json_response:
            def add_field_ids(rules):
                for rule in rules:
                    if rule.get("ruleType") == "condition":
                        if "field" in rule and "fieldId" not in rule:
                            field_name = rule["field"]
                            if field_name in field_mapping:
                                rule["fieldId"] = field_mapping[field_name]
                        # Add dataSourceId if missing
                        if "dataSource" in rule and "dataSourceId" not in rule:
                            data_source_name = rule["dataSource"]
                            # Find the data source ID from the data sources
                            for source_name, fields in data_sources.items():
                                if source_name == data_source_name and fields:
                                    rule["dataSourceId"] = fields[0].get("data_source_id", "N/A")
                                    break
                    elif rule.get("ruleType") == "conditionGroup":
                        if "conditions" in rule:
                            add_field_ids(rule["conditions"])
            
            add_field_ids(json_response["rules"])
        
        return json_response
        
    except Exception as e:
        print("error", e)
        raise HTTPException(status_code=500, detail=f"Error generating rule by Openai: {str(e)}")

# Pydantic Models
class RuleGenerationRequest(BaseModel):
    user_input: str
    client_id: Optional[int] = None
    logical_structure: Optional[str] = None
    auto_select_structure: Optional[bool] = True

class GeneratedRule(BaseModel):
    rules: List[Union[Condition, ConditionGroup]]
    logical_structure: Optional[str] = None
    topLevelConnector: Optional[str] = None

class ConfirmationMessage(BaseModel):
    message: str
    logical_structure: str
    user_message: str

class GeneralMessage(BaseModel):
    message: str

class DataSourceInfo(BaseModel):
    source_name: str
    fields: List[Dict[str, str]]

class RuleGenerationResponse(BaseModel):
    success: bool
    rule: Any = None
    logical_structures: Optional[List[str]] = None
    selected_structure: Optional[str] = None
    error_message: Optional[str] = None
    confirmation_message: Optional[ConfirmationMessage] = None
    general_message: Optional[GeneralMessage] = None
    data_sources_info: Optional[DataSourceInfo] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error_message: str

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatHistoryRequest(BaseModel):
    client_id: int
    message: ChatMessage

class SaveChatRequest(BaseModel):
    client_id: int
    chat_messages: List[ChatMessage]
    timestamp: Optional[str] = None

class ChatHistoryResponse(BaseModel):
    success: bool
    client_id: Optional[int] = None
    chat_messages: Optional[List[ChatMessage]] = None
    timestamp: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message: Optional[str] = None
    error_message: Optional[str] = None

class AddMessageRequest(BaseModel):
    client_id: int
    role: str  # "user" or "assistant"
    content: str

class AddMessageResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error_message: Optional[str] = None

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Mortgage Rule Generator API",
        "version": "1.0.0",
        "endpoints": {
            "/generate-rule": "POST - Generate mortgage rules from natural language",
            "/chat-history/{client_id}": "GET - Get chat history for a specific client",
            "/chat-history/save": "POST - Save complete chat history for a client",
            "/chat-history/add-message": "POST - Add a single message to existing chat history",
            "/chat-history/{client_id}": "DELETE - Clear chat history for a specific client",
            "/chat-history": "GET - Get all client IDs that have chat history",
            "/data-sources": "GET - Get available data sources and their columns",
            "/docs": "GET - API documentation",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        return {"status": "healthy", "openai_client": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.post("/generate-rule", response_model=RuleGenerationResponse)
async def generate_rule(request: RuleGenerationRequest) -> RuleGenerationResponse:
    print("================================================")
    print("REQUEST JSON")
    print("request", request)
    print("================================================")

    try:
        cleaned_input = request.user_input
        
        try:
            rule_dict = await generate_rule_with_openai_complex(cleaned_input, request.client_id)
            print("rule_dict", rule_dict)
            response_type = detect_response_type(rule_dict)
            print("response_type", response_type)

            # Prepare response content for chat history
            response_content = ""
            
            if response_type == "rule":
                response_content = f"Generated rule successfully: {json.dumps(rule_dict, indent=2)}"
                response = RuleGenerationResponse(
                    success=True,
                    rule=rule_dict,
                    message="Rule generated successfully"
                )
                
            elif response_type == "confirmation":
                confirmation_msg = ConfirmationMessage(
                    message=rule_dict.get("message", ""),
                    logical_structure=rule_dict.get("logical_structure", ""),
                    user_message=rule_dict.get("user_message", "Does this match your needs? If not, please explain what should change.")
                )
                
                response_content = f"{confirmation_msg.message}\nLogical structure: {confirmation_msg.logical_structure}\n{confirmation_msg.user_message}"
                response = RuleGenerationResponse(
                    success=True,
                    confirmation_message=confirmation_msg
                )
            elif response_type == "general":
                general_msg = GeneralMessage(
                    message=rule_dict.get("message", "")
                )
                
                response_content = general_msg.message
                response = RuleGenerationResponse(
                    success=True,
                    general_message=general_msg
                )
            elif response_type == "data_sources":
                # Handle data source information response
                data_sources_info = rule_dict.get("data_sources_info", {})
                response_content = "Here's the information about available data:\n"
                if isinstance(data_sources_info, dict):
                    source_name = data_sources_info.get("source_name", "Unknown")
                    response_content += f"Data Source: {source_name}\n"
                    for field in data_sources_info.get("fields", []):
                        response_content += f"- {field.get('field', 'Unknown')}: {field.get('description', 'No description')} (Type: {field.get('type', 'Unknown')})\n"
                
                response = RuleGenerationResponse(
                    success=True,
                    data_sources_info=data_sources_info,
                    general_message=GeneralMessage(message=response_content)
                )
            else:
                response_content = "I'm not sure how to respond to that. Could you please rephrase or ask about creating rules or data sources?"
                response = RuleGenerationResponse(
                    success=False,
                    error_message="Invalid response type",
                    general_message=GeneralMessage(message=response_content))
            
            if request.client_id:
                try:
                    # Save user message first
                    chat_db.append_message(request.client_id, "user", cleaned_input)
                    # Then save assistant response
                    chat_db.append_message(request.client_id, "assistant", response_content)
                except Exception as e:
                    print(f"Warning: Failed to save messages to chat history: {e}")
            
            # Log the exact response before returning
            print("=== GENERATED RULE RESPONSE ===")
            print(json.dumps(response.model_dump(), indent=2))
            print("=== END RESPONSE ===")
            
            return response
            
        except Exception as e:
            print("error", e)
            error_message = f"Error generating rule: {str(e)}"
            
            # Save user message and error to chat history if client_id is provided
            if request.client_id:
                try:
                    chat_db.append_message(request.client_id, "user", cleaned_input)
                    chat_db.append_message(request.client_id, "assistant", f"Error: {error_message}")
                except Exception as chat_e:
                    print(f"Warning: Failed to save error message to chat history: {chat_e}")
            
            return RuleGenerationResponse(
                success=False,
                error_message=error_message
            )
    
    except Exception as e:
        print("error", e)
        error_message = f"Unexpected error: {str(e)}"
        
        # Save user message and unexpected error to chat history if client_id is provided
        if request.client_id:
            try:
                chat_db.append_message(request.client_id, "user", cleaned_input)
                chat_db.append_message(request.client_id, "assistant", f"Unexpected error: {error_message}")
            except Exception as chat_e:
                print(f"Warning: Failed to save unexpected error to chat history: {chat_e}")
        
        return RuleGenerationResponse(
            success=False,
            error_message=error_message
        )

@app.get("/data-sources")
async def get_data_sources(client_id: Optional[int] = DEFAULT_CLIENT_ID):
    """Get available data sources for rule generation with rich field metadata"""
    try:
        data_sources = fetch_data_sources(client_id)
        
        # Calculate total fields across all sources
        total_fields = sum(len(fields) for fields in data_sources.values())
        
        return {
            "data_sources": data_sources,
            "total_sources": len(data_sources),
            "total_fields": total_fields,
            "client_id": client_id,
            "description": "Available data sources with field metadata for rule generation",
            "field_structure": {
                "field": "Field name used in rules",
                "fieldId": "Unique identifier for the field",
                "type": "Data type (string, integer, etc.)",
                "description": "Field description for context"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data sources: {str(e)}")

# Chat History Endpoints
@app.get("/chat-history/{client_id}", response_model=ChatHistoryResponse)
async def get_chat_history(client_id: int):
    """Get chat history for a specific client"""
    try:
        chat_data = chat_db.get_chat_history(client_id)
        
        if chat_data:
            return ChatHistoryResponse(
                success=True,
                client_id=chat_data["client_id"],
                chat_messages=[ChatMessage(**msg) for msg in chat_data["chat_messages"]],
                timestamp=chat_data["timestamp"],
                created_at=chat_data["created_at"],
                updated_at=chat_data["updated_at"]
            )
        else:
            return ChatHistoryResponse(
                success=True,
                client_id=client_id,
                chat_messages=[],
                message="No chat history found for this client"
            )
    
    except Exception as e:
        return ChatHistoryResponse(
            success=False,
            error_message=f"Error retrieving chat history: {str(e)}"
        )

@app.post("/chat-history/save", response_model=ChatHistoryResponse)
async def save_chat_history(request: SaveChatRequest):
    """Save complete chat history for a client"""
    try:
        # Convert Pydantic models to dict
        chat_messages_dict = [msg.model_dump() for msg in request.chat_messages]
        
        success = chat_db.save_chat_history(
            client_id=request.client_id,
            chat_messages=chat_messages_dict,
            timestamp=request.timestamp
        )
        
        if success:
            # Return the saved data
            saved_data = chat_db.get_chat_history(request.client_id)
            return ChatHistoryResponse(
                success=True,
                client_id=saved_data["client_id"],
                chat_messages=[ChatMessage(**msg) for msg in saved_data["chat_messages"]],
                timestamp=saved_data["timestamp"],
                created_at=saved_data["created_at"],
                updated_at=saved_data["updated_at"]
            )
        else:
            return ChatHistoryResponse(
                success=False,
                error_message="Failed to save chat history"
            )
    
    except Exception as e:
        return ChatHistoryResponse(
            success=False,
            error_message=f"Error saving chat history: {str(e)}"
        )

@app.post("/chat-history/add-message", response_model=AddMessageResponse)
async def add_message(request: AddMessageRequest):
    """Add a single message to existing chat history"""
    try:
        success = chat_db.append_message(
            client_id=request.client_id,
            role=request.role,
            content=request.content
        )
        
        if success:
            return AddMessageResponse(
                success=True,
                message=f"Message added successfully for client {request.client_id}"
            )
        else:
            return AddMessageResponse(
                success=False,
                error_message="Failed to add message"
            )
    
    except Exception as e:
        return AddMessageResponse(
            success=False,
            error_message=f"Error adding message: {str(e)}"
        )

@app.delete("/chat-history/{client_id}")
async def clear_chat_history(client_id: int):
    """Clear chat history for a specific client"""
    try:
        success = chat_db.clear_chat_history(client_id)
        
        if success:
            return {
                "success": True,
                "message": f"Chat history cleared for client {client_id}"
            }
        else:
            return {
                "success": False,
                "message": f"No chat history found for client {client_id}"
            }
    
    except Exception as e:
        return {
            "success": False,
            "error_message": f"Error clearing chat history: {str(e)}"
        }

@app.get("/chat-history")
async def get_all_clients():
    """Get all client IDs that have chat history"""
    try:
        clients = chat_db.get_all_clients()
        return {
            "success": True,
            "clients": clients,
            "total_clients": len(clients)
        }
    
    except Exception as e:
        return {
            "success": False,
            "error_message": f"Error retrieving clients: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)