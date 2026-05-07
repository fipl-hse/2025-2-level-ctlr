"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Exception raised when a seed URL does not follow the expected pattern (must start with http:// or https://, optionally with www.).
    """

class NumberOfArticlesOutOfRangeError(Exception):
    """
    Exception raised when the total number of articles is outside the permitted range (1–150).
    """

class IncorrectNumberOfArticlesError(Exception):
    """
    Exception raised when the total number of articles is not a positive integer (must be greater than zero).
    """

class IncorrectHeadersError(Exception):
    """
    Exception raised when headers are not supplied in the form of a dictionary.
    """

class IncorrectEncodingError(Exception):
    """
    Exception raised when encoding is not provided as a string.
    """

class IncorrectTimeoutError(Exception):
    """
    Exception raised when timeout is not an integer between 1 and 59 inclusive.
    """

class IncorrectVerifyError(Exception):
    """
    Exception raised when either verify_certificate or headless_mode is not a boolean (True/False).
    """


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
        self.dto = self._extract_config_content()
        self._validate_config_content()

        self._seed_urls = self.dto.seed_urls
        self._num_articles = self.dto.total_articles_to_find_and_parse
        self._headers = self.dto.headers
        self._encoding = self.dto.encoding
        self._timeout = self.dto.timeout
        self._should_verify_certificate = self.dto.should_verify_certificate
        self._headless_mode = self.dto.headless

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as file:
            config_data = json.load(file)
            
        config_dto = ConfigDTO(
            seed_urls=config_data.get('seed_urls', []),
            headers=config_data.get('headers', {}),
            timeout=config_data.get('timeout', 5),
            total_articles_to_find_and_parse=config_data.get('total_articles_to_find_and_parse', 10),
            encoding=config_data.get('encoding', 'utf-8'),
            should_verify_certificate=config_data.get('should_verify_certificate', True),
            headless=config_data.get('headless_mode', False)
    )

        return config_dto


    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        self._validate_seed_urls(self.dto.seed_urls)
        self._validate_articles_count(self.dto.total_articles_to_find_and_parse)
        self._validate_headers(self.dto.headers)
        self._validate_encoding(self.dto.encoding)
        self._validate_timeout(self.dto.timeout)
        self._validate_verify(self.dto.should_verify_certificate)
        self._validate_headless(self.dto.headless)

    def _validate_seed_urls(self, seed_urls: list) -> None:
        """Validate seed URLs pattern."""
        if not isinstance(seed_urls, list):
            raise IncorrectSeedURLError("Seed URLs must be a list")

        pattern = r'^https?://(www\.)?'
        for url in seed_urls:
            if not isinstance(url, str) or not re.match(pattern, url):
                raise IncorrectSeedURLError(f"Invalid seed URL: {url}")

    def _validate_articles_count(self, count: int) -> None:
        """Validate total number of articles."""
        if not isinstance(count, int) or count < 0:
            raise IncorrectNumberOfArticlesError(
                f"Number of articles must be a non-negative integer, got: {count}"
            )
        if count < 1 or count > 150:
            raise NumberOfArticlesOutOfRangeError(
                f"Number of articles must be between 1 and 150, got: {count}"
            )

    def _validate_headers(self, headers: dict) -> None:
        """Validate headers format."""
        if not isinstance(headers, dict):
            raise IncorrectHeadersError(
                f"Headers must be a dictionary, got: {type(headers)}"
            )

    def _validate_encoding(self, encoding: str) -> None:
        """Validate encoding format."""
        if not isinstance(encoding, str):
            raise IncorrectEncodingError(
                f"Encoding must be a string, got: {type(encoding)}"
            )

    def _validate_timeout(self, timeout: int) -> None:
        """Validate timeout value."""
        if not isinstance(timeout, int) or timeout <= 0 or timeout >= 60:
            raise IncorrectTimeoutError(
                f"Timeout must be a positive integer less than 60, got: {timeout}"
            )

    def _validate_verify(self, verify: bool) -> None:
        """Validate verify certificate mode."""
        if verify not in (True, False):
            raise IncorrectVerifyError(f"Verify must be True or False, got: {verify}")

    def _validate_headless(self, headless: bool) -> None:
        """Validate headless mode value."""
        if headless not in (True, False):
            raise IncorrectVerifyError(f"Headless mode must be True or False, got: {headless}")

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        """Validate seed URLs pattern."""
        return self.dto.seed_urls

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
        return self.dto.headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self.dto.encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self.dto.timeout

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
        return self.dto.headless


def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """
    try:
        response = requests.get(
            url,
            headers=config.get_headers(),
            timeout=config.get_timeout(),
            verify=config.get_verify_certificate()
        )
        response.encoding = config.get_encoding()
        return response
    except requests.RequestException:
        return None



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
        self._urls: list[str] = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        for link in article_bs.find_all('a', href=True):
            href = link.get('href', '')
            if '/vstrechi/' in href:
                if href.startswith('http'):
                    return href
                return urljoin('https://event.pishi.pro', href)
        return None

    def find_articles(self) -> None:
        """
        Find articles.
        """
        needed = self.config.get_num_articles()
        collected = []

        for seed in self.config.get_seed_urls():
            if len(collected) >= needed:
                break

            response = make_request(seed, self.config)
            if response is None or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            article_url = self._extract_url(soup)

            if article_url and article_url not in collected:
                collected.append(article_url)
                self._urls.append(article_url)

        self._urls = collected[:needed]

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self._urls


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
        text_parts = []
        for paragraph in article_soup.find_all(['p', 'div.article-text', 'div.content']):
            raw_text = paragraph.get_text(strip=True)
            if raw_text and len(raw_text) > 50:
                text_parts.append(raw_text)

        if not text_parts:
            body = article_soup.find('body')
            if body:
                text_parts.append(body.get_text(strip=True))

        self.article.text = '\n\n'.join(text_parts)

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('h1')
        if title_tag:
            self.article.title = title_tag.get_text(strip=True)
        else:
            self.article.title = "NOT FOUND"

        author_tag = article_soup.find(class_=re.compile(r'author', re.I))
        if author_tag:
            self.article.author = [author_tag.get_text(strip=True)]
        else:
            self.article.author = ["NOT FOUND"]

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
        response = make_request(self.full_url, self.config)
        if response is None or response.status_code != 200:
            return False

        soup = BeautifulSoup(response.text, 'html.parser')
        self._fill_article_with_text(soup)
        self._fill_article_with_meta_information(soup)

        return self.article


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    import shutil
    path = pathlib.Path(base_path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    prepare_environment(ASSETS_PATH)
    config = Config(CRAWLER_CONFIG_PATH)
    crawler = Crawler(config)
    crawler.find_articles()

    for idx, url in enumerate(crawler.get_search_urls(), start=1):
        parser = HTMLParser(full_url=url, article_id=idx, config=config)
        article = parser.parse()
        if article and article.text:
            to_raw(article, ASSETS_PATH)
            to_meta(article, ASSETS_PATH)


if __name__ == "__main__":
    main()
