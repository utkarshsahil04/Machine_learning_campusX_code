import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

def scrape_gamenation_homepage():
    """
    Scrapes game names and info from GameNation.in homepage and saves to JSON file
    """
    url = "https://gamenation.in"
    
    try:
        # Send GET request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Initialize data structure
        scraped_data = {
            "url": url,
            "scraped_at": datetime.now().isoformat(),
            "games": []
        }
        
        # Scrape game articles/posts
        # Try multiple common patterns for gaming websites
        articles = soup.find_all(['article', 'div'], class_=lambda x: x and any(
            term in str(x).lower() for term in ['post', 'article', 'card', 'item', 'game', 'product']
        ))
        
        for article in articles:
            game_data = {}
            
            # Try to find game name/title
            title = article.find(['h1', 'h2', 'h3', 'h4', 'h5'])
            if not title:
                title = article.find('a')
            
            if title:
                game_name = title.get_text(strip=True)
                if game_name:
                    game_data['name'] = game_name
            
            # Try to find game description/info
            # Look for paragraphs, divs with description/excerpt classes
            description = article.find(['p', 'div'], class_=lambda x: x and any(
                term in str(x).lower() for term in ['excerpt', 'description', 'summary', 'content', 'info']
            ))
            
            if not description:
                # Try to find any paragraph
                description = article.find('p')
            
            if description:
                game_info = description.get_text(strip=True)
                if game_info:
                    game_data['info'] = game_info
            
            # Try to find game link for more details
            link = article.find('a', href=True)
            if link:
                game_data['link'] = link['href']
            
            # Try to find category/genre
            category = article.find(class_=lambda x: x and any(
                term in str(x).lower() for term in ['category', 'genre', 'tag']
            ))
            if category:
                game_data['category'] = category.get_text(strip=True)
            
            # Try to find price if it's a store
            price = article.find(class_=lambda x: x and 'price' in str(x).lower())
            if price:
                game_data['price'] = price.get_text(strip=True)
            
            # Try to find date
            date = article.find(['time', 'span'], class_=lambda x: x and 'date' in str(x).lower())
            if date:
                game_data['date'] = date.get_text(strip=True)
            
            # Only add if we have at least a name
            if game_data.get('name'):
                scraped_data["games"].append(game_data)
        
        # Alternative: Look for specific game listings (like in tables or lists)
        game_lists = soup.find_all(['ul', 'ol'], class_=lambda x: x and 'game' in str(x).lower())
        for game_list in game_lists:
            items = game_list.find_all('li')
            for item in items:
                game_data = {}
                
                # Get game name
                title = item.find(['h1', 'h2', 'h3', 'h4', 'h5', 'a', 'strong'])
                if title:
                    game_data['name'] = title.get_text(strip=True)
                
                # Get game info
                text = item.get_text(strip=True)
                if text and game_data.get('name'):
                    # Remove the title from the text to get just the description
                    info = text.replace(game_data['name'], '').strip()
                    if info:
                        game_data['info'] = info
                
                if game_data.get('name'):
                    scraped_data["games"].append(game_data)
        
        # Remove duplicates based on game name
        seen_names = set()
        unique_games = []
        for game in scraped_data["games"]:
            if game['name'] not in seen_names:
                seen_names.add(game['name'])
                unique_games.append(game)
        
        scraped_data["games"] = unique_games
        
        # Save to JSON file
        filename = f"gamenation_games_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(scraped_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Data scraped successfully!")
        print(f"✓ Saved to: {filename}")
        print(f"\nSummary:")
        print(f"  - Games found: {len(scraped_data['games'])}")
        print(f"\nSample games:")
        for i, game in enumerate(scraped_data['games'][:5], 1):
            print(f"\n  {i}. {game.get('name', 'N/A')}")
            if game.get('info'):
                info_preview = game['info'][:100] + "..." if len(game['info']) > 100 else game['info']
                print(f"     Info: {info_preview}")
        
        return scraped_data
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching the website: {e}")
        return None
    except Exception as e:
        print(f"✗ Error scraping data: {e}")
        return None

if __name__ == "__main__":
    print("Starting GameNation.in game scraper...")
    print("=" * 50)
    scrape_gamenation_homepage()