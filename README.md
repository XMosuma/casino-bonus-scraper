# Casino bonus scraper
## Link: https://taupe-kitten-0580cb.netlify.app/

Fetches bonus pages for 3 casinos from one public source, uses a language model to turn
the free-text terms into structured fields, writes `bonuses.json`, and shows them in a
table on `index.html`.

## Install

```bash
python -m venv .venv 
.venv\Scripts\activate
pip install -r requirements.txt

winget install Ollama.Ollama
ollama pull llama3.2    
python scraper.py 

```



## Production Plan: Scaling to 200 Casinos

To take this project to production, I would deploy it on **AWS**, using an EC2 instance to run the Python scraper and host the backend. I would use **PostgreSQL** to store casino details, bonus information, source URLs, timestamps, and scraping history. I would enable automated daily database backups and retain backups in Amazon S3 so that data could be restored if necessary.

I would register a domain through a domain registrar and use **Amazon Route 53** for DNS management. I would secure the website with HTTPS using AWS Certificate Manager. For the frontend, I would keep using a static hosting service such as Netlify to reduce hosting costs.

I would schedule the scraper to run daily using **cron** on the server. The script would process casinos in batches, respect each website’s `robots.txt` rules, apply request timeouts and retries, and validate extracted data before updating the database. I would log each run and use Amazon CloudWatch to monitor execution, errors, and failed scraping jobs. I would configure alerts so that I am notified when a scheduled run fails or a casino’s source becomes unavailable.

For a small initial deployment, I would estimate a monthly cost of approximately **US$25–$60**, depending on the EC2 instance, storage, backups, monitoring, and traffic. Domain registration would be an additional annual expense. I would monitor actual usage and scale the infrastructure as the number of casinos and website traffic increase.

## five-line version
I used Claude in chat to write the scraper, the web page and the README, and Llama 3.2 (run locally with Ollama) as the model inside the scraper that extracts the bonus fields.
Llama was wrong on the Sunbet page. It returned a 5x wagering requirement and a “100%” welcome bonus, but the page only says “up to R1,000” and gives no wagering number.
I caught it by checking each row of bonuses.json against its source page. The page never mentions 5x or 100%.
I fixed it by adding a check to the script that nulls any value whose numbers don’t appear in the page text. It logs UNSUPPORTED and the table now shows only values the page supports.
Llama also labelled the Betway page “Spina Zonke” (Betway’s casino brand, mentioned in passing), which I fixed by passing the page title and URL into the prompt. It still misses some values, such as Hollywoodbets’ 20x wagering, so I left those empty rather than guess.


## **Time taken:
 Approximately 3 hours, including development, debugging, testing, and deployment. Some documentation and final checks were completed afterward.