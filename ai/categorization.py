"""
AI-powered custom category classification and impact analysis.
Uses LLM to intelligently categorize custom spending items and determine
which economic indicators (fuel, forex, food) affect them.
"""
import json
from ai.insights import generate_insight

class CustomCategoryClassifier:
    """Classify custom spending categories using AI"""
    
    MAIN_CATEGORIES = ["Transport", "Food & Groceries", "Utilities", "Other"]
    ECONOMIC_INDICATORS = ["fuel", "forex", "food_basket"]
    
    @staticmethod
    async def classify_custom_items(custom_categories: list[dict]):
        """
        Analyze custom spending items and classify them.
        
        Args:
            custom_categories: List of custom items, each with 'label' and 'value' (cost)
        
        Returns:
            List of with AI classification and impact analysis
        """
        if not custom_categories:
            return []
        
        classifications = []
        
        for item in custom_categories:
            try:
                item_name = item.get("label", "Unknown")
                monthly_cost = float(item.get("value", 0))
                
                if monthly_cost <= 0:
                    continue
                
                # Get AI classification
                classification = await CustomCategoryClassifier._classify_single_item(
                    item_name, monthly_cost
                )
                classifications.append(classification)
                
            except Exception as e:
                print(f"Error classifying {item.get('label', 'unknown')}: {str(e)}")
                continue
        
        return classifications
    
    @staticmethod
    async def _classify_single_item(item_name: str, monthly_cost: float):
        """
        Classify a single custom spending item using AI.
        """
        prompt = f"""
        Analyze this spending item and classify it:
        
        Item: {item_name}
        Monthly Cost: KES {monthly_cost}
        
        Your task:
        1. Classify into ONE of: Transport, Food & Groceries, Utilities, Other
        2. Determine if affected by:
           - Fuel prices (petrol, diesel, kerosene) - e.g., generators, vehicles, transport
           - Forex rates (USD/KES) - e.g., imported goods, insurance, subscriptions
           - Food basket prices - e.g., groceries, food-related items
        3. Estimate the % impact from economic factors (0-100%)
        4. Provide brief reasoning
        
        Return ONLY valid JSON (no markdown, no code blocks):
        {{
            "classified_category": "Transport|Food & Groceries|Utilities|Other",
            "affected_by_fuel": true/false,
            "affected_by_forex": true/false,
            "affected_by_food": true/false,
            "estimated_impact_pct": 0-100,
            "reasoning": "Brief explanation (max 100 chars)"
        }}
        """
        
        try:
            # Call AI to classify
            ai_response = await generate_insight("custom_category_classification", {"item": item_name})
            
            # Parse response
            classification_data = CustomCategoryClassifier._parse_ai_response(ai_response)
            
            return {
                "custom_item_name": item_name,
                "classified_category": classification_data.get("classified_category", "Other"),
                "monthly_cost": monthly_cost,
                "affected_by_fuel": classification_data.get("affected_by_fuel", False),
                "affected_by_forex": classification_data.get("affected_by_forex", False),
                "affected_by_food": classification_data.get("affected_by_food", False),
                "estimated_impact_pct": classification_data.get("estimated_impact_pct", 0),
                "reasoning": classification_data.get("reasoning", "Classified by AI")
            }
            
        except Exception as e:
            # Fallback classification if AI fails
            print(f"AI classification failed for {item_name}, using fallback: {str(e)}")
            return CustomCategoryClassifier._fallback_classification(item_name, monthly_cost)
    
    @staticmethod
    def _parse_ai_response(ai_response: dict) -> dict:
        """
        Parse AI response. Handles both direct dict and string responses.
        """
        if isinstance(ai_response, dict):
            return ai_response
        
        if isinstance(ai_response, str):
            try:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except:
                pass
        
        return {}
    
    @staticmethod
    def _fallback_classification(item_name: str, monthly_cost: float):
        """
        Fallback classification using keyword matching when AI fails.
        """
        item_lower = item_name.lower()
        
        # Fuel/Transport keywords
        if any(kw in item_lower for kw in ["fuel", "petrol", "diesel", "transport", "taxi", "matatu", 
                                            "uber", "boda", "motorcycle", "parking", "toll", "car"]):
            return {
                "custom_item_name": item_name,
                "classified_category": "Transport",
                "monthly_cost": monthly_cost,
                "affected_by_fuel": True,
                "affected_by_forex": False,
                "affected_by_food": False,
                "estimated_impact_pct": 70,
                "reasoning": "Matched transport keywords"
            }
        
        # Food keywords
        elif any(kw in item_lower for kw in ["food", "grocery", "grocery", "vegetables", "fruits", 
                                              "meat", "fish", "cooking", "meal", "lunch", "dinner"]):
            return {
                "custom_item_name": item_name,
                "classified_category": "Food & Groceries",
                "monthly_cost": monthly_cost,
                "affected_by_fuel": False,
                "affected_by_forex": False,
                "affected_by_food": True,
                "estimated_impact_pct": 60,
                "reasoning": "Matched food keywords"
            }
        
        # Utilities keywords
        elif any(kw in item_lower for kw in ["electricity", "water", "gas", "generator", "diesel-gen",
                                              "solar", "power", "utility", "bill", "energy"]):
            return {
                "custom_item_name": item_name,
                "classified_category": "Utilities",
                "monthly_cost": monthly_cost,
                "affected_by_fuel": True,
                "affected_by_forex": True,
                "affected_by_food": False,
                "estimated_impact_pct": 50,
                "reasoning": "Matched utilities keywords"
            }
        
        # Imported/Forex keywords
        elif any(kw in item_lower for kw in ["subscription", "wifi", "internet", "netflix", "spotify",
                                              "insurance", "medicine", "laptop", "phone", "device",
                                              "imported", "amazon", "online"]):
            return {
                "custom_item_name": item_name,
                "classified_category": "Other",
                "monthly_cost": monthly_cost,
                "affected_by_fuel": False,
                "affected_by_forex": True,
                "affected_by_food": False,
                "estimated_impact_pct": 40,
                "reasoning": "Likely forex-affected import"
            }
        
        # Default: Other
        else:
            return {
                "custom_item_name": item_name,
                "classified_category": "Other",
                "monthly_cost": monthly_cost,
                "affected_by_fuel": False,
                "affected_by_forex": False,
                "affected_by_food": False,
                "estimated_impact_pct": 20,
                "reasoning": "Classified as Other (non-essential)"
            }
    
    @staticmethod
    def calculate_custom_impact(
        custom_analysis: dict,
        fuel_change_pct: float,
        forex_change_pct: float,
        food_change_pct: float
    ) -> dict:
        """
        Calculate actual impact on a custom item based on economic indicators.
        
        Returns:
            {
                "monthly_impact_kes": float,
                "impact_pct": float,
                "direction": "up" | "down" | "stable",
                "primary_driver": str,
                "breakdown": dict
            }
        """
        
        monthly_cost = custom_analysis.monthly_cost
        impact_kes = 0.0
        
        # Calculate impact from each affected indicator
        impacts = {}
        
        if custom_analysis.affected_by_fuel:
            fuel_impact = (monthly_cost * fuel_change_pct) / 100
            impacts["fuel"] = fuel_impact
            impact_kes += fuel_impact
        
        if custom_analysis.affected_by_forex:
            forex_impact = (monthly_cost * forex_change_pct) / 100
            impacts["forex"] = forex_impact
            impact_kes += forex_impact
        
        if custom_analysis.affected_by_food:
            food_impact = (monthly_cost * food_change_pct) / 100
            impacts["food"] = food_impact
            impact_kes += food_impact
        
        # Determine primary driver
        primary_driver = "none"
        if impacts:
            primary_driver = max(impacts, key=lambda k: abs(impacts[k]))
        
        # Calculate percentage change
        change_pct = (impact_kes / monthly_cost * 100) if monthly_cost > 0 else 0
        direction = "up" if change_pct > 0 else ("down" if change_pct < 0 else "stable")
        
        return {
            "monthly_cost": monthly_cost,
            "monthly_impact_kes": round(impact_kes, 2),
            "impact_pct": round(change_pct, 2),
            "direction": direction,
            "primary_driver": primary_driver,
            "breakdown": {k: round(v, 2) for k, v in impacts.items()}
        }
