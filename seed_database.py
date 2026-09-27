import logging
from google.cloud import firestore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Hardcoded Project ID string as required for Agent Platform compatibility
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-c74d36ed01ba"

SAMPLE_RECIPES = [
    {
        "id": "avocado-toast",
        "title": "Avocado & Poached Egg Toast",
        "cuisine": "American",
        "prep_time_mins": 10,
        "servings": 2,
        "ingredients": [
            "2 slices sourdough bread",
            "1 ripe avocado",
            "2 large eggs",
            "1 tbsp lemon juice",
            "Pinch of red pepper flakes",
            "Salt and black pepper to taste"
        ],
        "instructions": "Toast sourdough slices. Mash avocado with lemon juice, salt, and pepper. Poach eggs in simmering water for 3 mins. Spread avocado on toast, top with poached egg and pepper flakes.",
        "dietary_tags": ["vegetarian", "dairy-free"],
        "calories_per_serving": 320
    },
    {
        "id": "mediterranean-chickpea-salad",
        "title": "Mediterranean Chickpea & Feta Salad",
        "cuisine": "Mediterranean",
        "prep_time_mins": 15,
        "servings": 4,
        "ingredients": [
            "2 cans (15 oz) chickpeas, rinsed",
            "1 cucumber, diced",
            "1 cup cherry tomatoes, halved",
            "1/2 cup crumbled feta cheese",
            "1/4 cup extra virgin olive oil",
            "2 tbsp red wine vinegar",
            "1 tsp dried oregano"
        ],
        "instructions": "Combine chickpeas, cucumber, cherry tomatoes, and feta in a bowl. Whisk olive oil, red wine vinegar, and oregano together. Toss salad with dressing and serve chilled.",
        "dietary_tags": ["vegetarian", "gluten-free"],
        "calories_per_serving": 290
    },
    {
        "id": "thai-green-curry",
        "title": "Thai Green Vegetable Curry",
        "cuisine": "Thai",
        "prep_time_mins": 25,
        "servings": 4,
        "ingredients": [
            "2 tbsp green curry paste",
            "1 can (14 oz) coconut milk",
            "1 cup tofu or chicken, cubed",
            "1 cup bell peppers, sliced",
            "1 cup bamboo shoots",
            "1 tbsp soy sauce",
            "Fresh basil leaves for garnish"
        ],
        "instructions": "Sauté green curry paste in 2 tbsp coconut milk until fragrant. Add remaining coconut milk and bring to a simmer. Add tofu/chicken and vegetables; cook for 12 mins. Stir in soy sauce and top with basil.",
        "dietary_tags": ["vegan", "gluten-free", "dairy-free"],
        "calories_per_serving": 380
    },
    {
        "id": "classic-margherita-pizza",
        "title": "Classic Artisan Margherita Pizza",
        "cuisine": "Italian",
        "prep_time_mins": 20,
        "servings": 3,
        "ingredients": [
            "1 pizza dough ball",
            "1/2 cup crushed San Marzano tomatoes",
            "4 oz fresh mozzarella, sliced",
            "Handful of fresh basil leaves",
            "1 tbsp olive oil"
        ],
        "instructions": "Preheat oven to 475°F (245°C). Stretch dough into a 12-inch circle. Spread tomatoes thinly, top with mozzarella slices. Bake for 10-12 mins until crust is golden. Garnish with fresh basil and olive oil drizzle.",
        "dietary_tags": ["vegetarian"],
        "calories_per_serving": 410
    }
]

def seed():
    logger.info(f"Connecting to Firestore for project: {FIRESTORE_PROJECT_ID}")
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)
    recipes_ref = db.collection("recipes")

    for recipe in SAMPLE_RECIPES:
        doc_id = recipe["id"]
        recipes_ref.document(doc_id).set(recipe)
        logger.info(f"Seeded recipe: {doc_id} -> {recipe['title']}")

    logger.info("Successfully seeded Firestore recipes collection!")

if __name__ == "__main__":
    seed()
