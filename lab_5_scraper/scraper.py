"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import shutil
import pathlib
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup, Tag

from core_utils.constants import CRAWLER_CONFIG_PATH, ASSETS_PATH

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO
from core_utils.article.io import to_raw, to_meta

class IncorrectSeedURLError(Exception):
    """Raised when seed URL does not match expected pattern."""
    pass

class NumberOfArticlesOutOfRangeError(Exception):
    """Raised when total number of articles is out of range 1-150."""
    pass

class IncorrectNumberOfArticlesError(Exception):
    """Raised when total number of articles is not integer or less than 0."""
    pass

class IncorrectHeadersError(Exception):
    """Raised when headers are not a dictionary."""
    pass

class IncorrectEncodingError(Exception):
    """Raised when encoding is not a string."""
    pass

class IncorrectTimeoutError(Exception):
    """Raised when timeout is not a positive integer less than 60."""
    pass

class IncorrectVerifyError(Exception):
    """Raised when verify certificate or headless mode are not boolean."""
    pass


class Config:
    """
    Class for unpacking and validating configurations.
    """

    def __init__(self, path_to_config: pathlib.Path) -> None:
        """
        Initialize an instance of the Config class.

        Args:
            path_to_config (pathlib.Path): Path to configuration.
        """
        self.path_to_config = path_to_config

        self._validate_config_content()

        config_dto = self._extract_config_content()

        self._seed_urls = config_dto.seed_urls
        self._headers = config_dto.headers
        self._num_articles = config_dto.total_articles
        self._encoding = config_dto.encoding
        self._timeout = config_dto.timeout
        self._should_verify_certificate = config_dto.should_verify_certificate
        self._headless_mode = config_dto.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as file:
            config_data = json.load(file)

        return ConfigDTO(
            seed_urls=config_data.get('seed_urls', []),
            headers=config_data.get('headers', {}),
            total_articles_to_find_and_parse=config_data.get('total_articles_to_find_and_parse', 0),
            encoding=config_data.get('encoding', 'utf-8'),
            timeout=config_data.get('timeout', 10),
            should_verify_certificate=config_data.get('should_verify_certificate', True),
            headless_mode=config_data.get('headless_mode', False)
        )


    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config_dto = self._extract_config_content()

        seed_urls = config_dto.seed_urls
        if not isinstance(seed_urls, list):
            raise IncorrectSeedURLError("Seed URLs must be a list")

        url_pattern = re.compile(r"https?://(www\.)?") 
        for url in seed_urls:
            if not isinstance(url, str):
                raise IncorrectSeedURLError(f"Seed URL must be a string, got {type(url)}")
            if not url_pattern.match(url):
                raise IncorrectSeedURLError(f"Invalid seed URL format: {url}")

        total_articles = config_dto.total_articles
        
        if isinstance(total_articles, bool):
            raise IncorrectNumberOfArticlesError(
                f"Total articles must be an integer, got {type(total_articles).__name__}"
            )

        if not isinstance(total_articles, int):
            raise IncorrectNumberOfArticlesError(
                f"Total articles must be an integer, got {type(total_articles)}"
            )

        if total_articles < 0:
            raise IncorrectNumberOfArticlesError(
                f"Total articles cannot be negative: {total_articles}"
            )

        if total_articles < 1 or total_articles > 150:
            raise NumberOfArticlesOutOfRangeError(
                f"Total articles must be between 1 and 150, got {total_articles}"
            )

        headers = config_dto.headers
        if not isinstance(headers, dict):
            raise IncorrectHeadersError(
                f"Headers must be a dictionary, got {type(headers)}"
            )

        encoding = config_dto.encoding
        if not isinstance(encoding, str):
            raise IncorrectEncodingError(
                f"Encoding must be a string, got {type(encoding)}"
            )

        timeout = config_dto.timeout
        if not isinstance(timeout, int):
            raise IncorrectTimeoutError(
                f"Timeout must be an integer, got {type(timeout)}"
            )

        if timeout <= 0:
            raise IncorrectTimeoutError(
                f"Timeout must be positive, got {timeout}"
            )

        if timeout >= 60:
            raise IncorrectTimeoutError(
                f"Timeout must be less than 60, got {timeout}"
            )

        should_verify = config_dto.should_verify_certificate
        if not isinstance(should_verify, bool):
            raise IncorrectVerifyError(
                f"should_verify_certificate must be boolean, got {type(should_verify)}"
            )

        headless_mode = config_dto.headless_mode
        if not isinstance(headless_mode, bool):
            raise IncorrectVerifyError(
                f"headless_mode must be boolean, got {type(headless_mode)}"
            )


    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self._seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self._num_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self._headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self._encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self._timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self._should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self._headless_mode


def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """
    headers = config.get_headers()
    timeout = config.get_timeout()
    verify = config.get_verify_certificate()

    response = requests.get(url, headers=headers, timeout=timeout, verify=verify)

    return response


class Crawler:
    """
    Crawler implementation.
    """

    #: Url pattern
    url_pattern: re.Pattern | str

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self.config = config
        self.urls = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        base_url = self.config.get_seed_urls()[0]
        if article_bs.name == "a" and article_bs.get("href"):
            href = article_bs.get("href")
            return urljoin(base_url, href)

        link = article_bs.find("a")
        if link and link.get("href"):
            return urljoin(base_url, link.get("href"))

        return ""

    def find_articles(self) -> None:
        """
        Find articles.
        """
        seed_urls = self.config.get_seed_urls()
        target_count = self.config.get_num_articles()

        for seed_url in seed_urls:
            if len(self.urls) >= target_count:
                break

            pages_to_process = [
                (seed_url, lambda s: s.find_all("a", class_="read-more")),
                (seed_url.rstrip("/") + "/archive_news", lambda s: s.find_all("a", string="подробнее")),
            ]

            for page_url, find_links in pages_to_process:
                if len(self.urls) >= target_count:
                    break

                try:
                    response = make_request(page_url, self.config)
                except requests.exceptions.RequestException as e:
                    print(f"Request failed: {e}")
                    continue

                if response.status_code != 200:
                    print(f"Warning: Could not fetch {page_url}, status {response.status_code}")
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                links = find_links(soup)

                for link in links:
                    url = self._extract_url(link)
                    if url and url not in self.urls:
                        self.urls.append(url)
                        print(f"Found {len(self.urls)}: {url}")
                        if len(self.urls) >= target_count:
                            break

        print(f"Total found: {len(self.urls)} article URLs (need {target_count})")


    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


# 10


class CrawlerRecursive(Crawler):
    """
    Recursive implementation.

    Get one URL of the title page and find requested number of articles recursively.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the CrawlerRecursive class.

        Args:
            config (Config): Configuration
        """
        super().__init__(config)

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """


# 4, 6, 8, 10


class HTMLParser:
    """
    HTMLParser implementation.
    """

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initialize an instance of the HTMLParser class.

        Args:
            full_url (str): Site url
            article_id (int): Article id
            config (Config): Configuration
        """
        self.full_url = full_url
        self.article_id = article_id
        self.config = config
        self.article = Article(url=full_url, article_id=article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        for script in article_soup(["script", "style"]):
            script.decompose()

        text_container = article_soup.find('div', style=lambda x: x and 'text-align: justify' in x)

        if not text_container:
            print(f"Warning: Could not find text container for {self.full_url}")
            self.article.text = ""
            return

        for br in text_container.find_all('br'):
            br.replace_with('\n')

        structured_tags = text_container.find_all(['p', 'strong', 'em', 'h1', 'h2', 'h3', 'h4'])

        if structured_tags:
            text_parts = []
            for tag in structured_tags:
                text = tag.get_text(strip=True)
                if text:
                    text_parts.append(text)
            self.article.text = '\n\n'.join(text_parts)
        else:
            full_text = text_container.get_text()
            lines = [line.strip() for line in full_text.split('\n') if line.strip()]
            self.article.text = '\n\n'.join(lines)

        print(f"Extracted {len(self.article.text)} characters")


    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('h1', class_='col-title')
        if not title_tag:
            title_tag = article_soup.find('h1')
        if not title_tag:
            title_tag = article_soup.find('title')

        if title_tag:
            self.article.title = title_tag.get_text(strip=True)
        else:
            self.article.title = "NOT FOUND"

        author_tag = article_soup.find('span', class_='author')
        if not author_tag:
            author_tag = article_soup.find('div', class_='author')
        if not author_tag:
            author_tag = article_soup.find('meta', attrs={'name': 'author'})
            if author_tag and author_tag.get('content'):
                self.article.author = [author_tag['content']]
                return

        if author_tag:
            self.article.author = [author_tag.get_text(strip=True)]
        else:
            self.article.author = ["NOT FOUND"]

        self.article.topics = []

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        try:
            parts = date_str.strip().split('.')
            if len(parts) == 3:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                return datetime.datetime(year, month, day)
        except (ValueError, AttributeError):
            pass

        return datetime.datetime.now()

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
        except requests.exceptions.RequestException as e:
            print(f"Request failed for {self.full_url}: {e}")
            return self.article

        if response.status_code != 200:
            print(f"Warning: Could not fetch {self.full_url}, status {response.status_code}")
            return self.article

        article_bs = BeautifulSoup(response.text, 'html.parser')
        self._fill_article_with_text(article_bs)
        self._fill_article_with_meta_information(article_bs)

        return self.article


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    base_path = pathlib.Path(base_path)

    if base_path.exists():
        shutil.rmtree(base_path)

    base_path.mkdir(parents=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    config = Config(CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)

    print("Step 1: Crawling for article URLs...")
    crawler = Crawler(config)
    crawler.find_articles()
    article_urls = crawler.urls

    target_count = min(config.get_num_articles(), len(article_urls))
    print(f"Target: {target_count} articles, Found: {len(article_urls)}")

    print("\nStep 2: Parsing and saving articles...")
    for i, url in enumerate(article_urls[:target_count], 1):
        print(f"\n--- Processing article {i}/{target_count} ---")
        print(f"URL: {url}")

        try:
            parser = HTMLParser(url, i, config)
            article = parser.parse()

            to_raw(article)
            print(f"✓ Saved text to {article.get_raw_text_path()}")

            to_meta(article)
            print(f"✓ Saved metadata to {article.get_meta_file_path()}")

        except (ValueError, KeyError, TypeError) as e:
            print(f"✗ Error processing article {i}: {e}")
            continue

    print("\n" + "="*50)
    print(f"Done! Saved {target_count} articles to {ASSETS_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()