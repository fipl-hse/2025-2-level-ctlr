"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
import shutil
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """Seed URL does not match standard pattern."""


class NumberOfArticlesOutOfRangeError(Exception):
    """Total number of articles is out of range from 1 to 150."""


class IncorrectNumberOfArticlesError(Exception):
    """Total number of articles is not integer or less than 0."""


class IncorrectHeadersError(Exception):
    """Headers are not in a form of dictionary."""


class IncorrectEncodingError(Exception):
    """Encoding must be specified as a string."""


class IncorrectTimeoutError(Exception):
    """Timeout value must be a positive integer less than 60."""


class IncorrectVerifyError(Exception):
    """Verify certificate and headless mode values must be bool."""

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
        self._num_articles = config_dto.total_articles
        self._headers = config_dto.headers
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
        with open(self.path_to_config, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return ConfigDTO(
            seed_urls=data.get('seed_urls', []),
            total_articles_to_find_and_parse=data.get('total_articles_to_find_and_parse', 0),
            headers=data.get('headers', {}),
            encoding=data.get('encoding', ''),
            timeout=data.get('timeout', 0),
            should_verify_certificate=data.get('should_verify_certificate', True),
            headless_mode=data.get('headless_mode', False)
        )

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config_dto = self._extract_config_content()
        if not isinstance(config_dto.seed_urls, list):
            raise IncorrectSeedURLError(
                "Seed URLs must be a list of strings, not a single string"
            )
        for url in config_dto.seed_urls:
            if not isinstance(url, str) or not re.match(r'https?://.*', url):
                raise IncorrectSeedURLError(
                    f"Seed URL {url} does not match pattern 'https?://'"
                )
        if not isinstance(config_dto.total_articles, int):
            raise IncorrectNumberOfArticlesError(
                "Total number of articles must be integer"
            )
        if config_dto.total_articles <= 0:
            raise IncorrectNumberOfArticlesError(
                "Total number of articles must be positive"
            )
        if config_dto.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError(
                "Total number of articles must be <= 150"
            )
        if not isinstance(config_dto.headers, dict):
            raise IncorrectHeadersError("Headers must be a dictionary")
        if not isinstance(config_dto.encoding, str) or not config_dto.encoding:
            raise IncorrectEncodingError("Encoding must be a non-empty string")
        if not isinstance(config_dto.timeout, int) or config_dto.timeout <= 0:
            raise IncorrectTimeoutError("Timeout must be a positive integer")
        if config_dto.timeout > 60:
            raise IncorrectTimeoutError("Timeout must be less than 60")
        if not isinstance(config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError("Verify certificate must be bool")
        if not isinstance(config_dto.headless_mode, bool):
            raise IncorrectVerifyError("Headless mode must be bool")

       

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
    response = requests.get(
        url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate()
    )
    response.encoding = config.get_encoding()
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
        href = article_bs.get('href', '').strip()
        if not href:
            return ''
        
        if href.startswith('#') or href.startswith('javascript:'):
            return ''
        
        full_url = urllib.parse.urljoin('https://tarranova.lib.ru', href)
        
        if 'tarranova.lib.ru' not in full_url:
            return ''
        
        if full_url.rstrip('/') in ['https://tarranova.lib.ru',
                                      'https://tarranova.lib.ru/index.html',
                                      'https://tarranova.lib.ru/index.htm']:
            return ''
        
        if '#' in full_url:
            full_url = full_url.split('#')[0]
        
        return full_url
        

    def find_articles(self) -> None:
        """
        Find articles.
        """
        seed_urls = self.config.get_seed_urls()
        max_articles = self.config.get_num_articles()
        self.urls = []
        
        for seed_url in seed_urls:
            if len(self.urls) >= max_articles:
                break
                
            try:
                response = make_request(seed_url, self.config)
                if response.status_code != 200:
                    continue
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    if len(self.urls) >= max_articles:
                        break
                        
                    url = self._extract_url(link)
                    if url and (url.endswith('.htm') or url.endswith('.txt')):
                        if url not in self.urls:
                            self.urls.append(url)
            except Exception:
                continue

        
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
        for tag in article_soup.find_all(['script', 'style']):
            tag.decompose()

        body = article_soup.find('body')
        if body:
            text = body.get_text(separator='\n', strip=True)
        else:
            text = article_soup.get_text(separator='\n', strip=True)

        if not text or len(text) < 50:
            pre_tag = article_soup.find('pre')
            if pre_tag:
                text = pre_tag.get_text(separator='\n', strip=True)
            else:
                text = article_soup.get_text(separator='\n', strip=True)

        self.article.text = text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        text_content = article_soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]

        title_tag = article_soup.find('title')
        if title_tag and title_tag.string and title_tag.string.strip():
            title_text = title_tag.string.strip()
            title_text = re.sub(r'^TarraNova\s*[:–—-]\s*', '', title_text)
            if title_text:
                self.article.title = title_text

        if not self.article.title:
            for header_tag in article_soup.find_all(['h1', 'h2', 'h3']):
                header_text = header_tag.get_text(strip=True)
                if header_text and len(header_text) > 3:
                    self.article.title = header_text
                    break
        
        if not self.article.title:
            for line in lines:
                if len(line) > 5 and not line.startswith('<') and not line.startswith('http'):
                    self.article.title = line
                    break

        if not self.article.title:
            self.article.title = "NOT FOUND"

        author_found = False
        author_keywords = ['Автор:', 'Author:', 'Перевод:', 'Переводчик:', '©']

        for keyword in author_keywords:
            pattern = re.escape(keyword) + r'\s*(.+?)(?:\n|$)'
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                author_name = match.group(1).strip()
                if author_name and len(author_name) > 1:
                    self.article.author = [author_name]
                    author_found = True
                    break

        if not author_found:
            h1_tags = article_soup.find_all('h1')
            for h1 in h1_tags:
                h1_text = h1.get_text(strip=True)
                if h1_text and len(h1_text) > 3 and 'TarraNova' not in h1_text:
                    self.article.author = [h1_text]
                    author_found = True
                    break

        if not author_found:
            for i, line in enumerate(lines):
                if ('автор' in line.lower() or 'author' in line.lower()) and len(line) < 100:
                    # Try to extract name from this line or next line
                    name_match = re.search(r'(?:автор|author)\s*[:–—-]?\s*(.+)', line, re.IGNORECASE)
                    if name_match and name_match.group(1).strip():
                        self.article.author = [name_match.group(1).strip()]
                        author_found = True
                        break
                    elif i + 1 < len(lines) and lines[i + 1]:
                        self.article.author = [lines[i + 1]]
                        author_found = True
                        break

        if not author_found:
            self.article.author = ["NOT FOUND"]

        self.article.date = datetime.datetime.now()

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        return datetime.datetime.now()

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            if response.status_code != 200:
                return self.article

            soup = BeautifulSoup(response.text, 'html.parser')
            self._fill_article_with_text(soup)
            self._fill_article_with_meta_information(soup)

            return self.article
        except Exception:
            return self.article


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    path = pathlib.Path(base_path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)



def main() -> None:
    """
    Entrypoint for scraper module.
    """
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)

    prepare_environment(ASSETS_PATH)

    crawler = Crawler(config=configuration)
    crawler.find_articles()

    print(f"Found {len(crawler.urls)} article URLs")

    prepare_environment(ASSETS_PATH)

    saved_count = 0
    for url in crawler.urls:
        parser = HTMLParser(full_url=url, article_id=saved_count + 1, config=configuration)
        article = parser.parse()

        if article and isinstance(article, Article):
            to_raw(article)
            to_meta(article)
            saved_count += 1
            print(f"  Saved: {saved_count}_raw.txt and {saved_count}_meta.json")
        else:
            print(f"  Failed to parse: {url}")

    print(f"Scraping completed! Saved {saved_count} articles.")



if __name__ == "__main__":
    main()
