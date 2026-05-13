"""
Crawler implementation.
"""

import datetime
import json
import pathlib
import re
import shutil
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_raw, to_meta
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """Seed URL does not match standard pattern."""
    pass


class NumberOfArticlesOutOfRangeError(Exception):
    """Number of articles out of range 1..150."""
    pass


class IncorrectNumberOfArticlesError(Exception):
    """Number of articles is not a positive integer."""
    pass


class IncorrectHeadersError(Exception):
    """Headers are not a dictionary."""
    pass


class IncorrectEncodingError(Exception):
    """Encoding is not a string."""
    pass


class IncorrectTimeoutError(Exception):
    """Timeout not in 1..60."""
    pass


class IncorrectVerifyError(Exception):
    """Verify certificate or headless mode is not boolean."""
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
        self._path = path_to_config
        self._load_and_validate()


    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        pass


    def _load_and_validate(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        with open(self._path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        seed_urls = data.get('seed_urls', [])
        total = data.get('total_articles_to_find_and_parse', 0)
        headers = data.get('headers', {})
        encoding = data.get('encoding', 'utf-8')
        timeout = data.get('timeout', 5)
        verify = data.get('should_verify_certificate', True)
        headless = data.get('headless_mode', False)

        if not isinstance(seed_urls, list):
            raise IncorrectSeedURLError("seed_urls must be a list")
        url_pattern = re.compile(r'https?://(www\.)?')
        for url in seed_urls:
            if not isinstance(url, str) or not url_pattern.match(url):
                raise IncorrectSeedURLError(f"Invalid seed URL: {url}")

        if not isinstance(total, int) or total <= 0:
            raise IncorrectNumberOfArticlesError("total_articles must be positive integer")
        if total > 150:
            raise NumberOfArticlesOutOfRangeError("total_articles must not exceed 150")

        if not isinstance(headers, dict):
            raise IncorrectHeadersError("headers must be a dict")
        if not isinstance(encoding, str):
            raise IncorrectEncodingError("encoding must be a string")
        if not isinstance(timeout, int) or timeout <= 0 or timeout > 60:
            raise IncorrectTimeoutError("timeout must be integer 1..60")
        if not isinstance(verify, bool):
            raise IncorrectVerifyError("should_verify_certificate must be boolean")
        if not isinstance(headless, bool):
            raise IncorrectVerifyError("headless_mode must be boolean")

        self._seed_urls = seed_urls
        self._total = total
        self._headers = headers
        self._encoding = encoding
        self._timeout = timeout
        self._verify = verify
        self._headless = headless


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
        return self._total


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
        return self._verify


    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self._headless


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
    url_pattern: re.Pattern | str = re.compile(r'')

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self.config = config
        self.urls = []

    def _extract_url(self, tag: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = tag.get('href', '')
        return urljoin('https://www.netslova.ru', href)

    def find_articles(self) -> None:
        """
        Find articles.
        """
        self.urls = self.config.get_seed_urls()
        needed = self.config.get_num_articles()
        if len(self.urls) > needed:
            self.urls = self.urls[:needed]

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
        pass


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
        for elem in article_soup(['script', 'style', 'nav', 'header', 'footer']):
            elem.decompose()
        content = article_soup.find('pre')
        if not content:
            content = article_soup.find('div', class_='text')
        if not content:
            content = article_soup.find('body')
        if content:
            paragraphs = content.find_all(['p', 'pre', 'div'])
            if paragraphs:
                text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)
            else:
                text = content.get_text(strip=True)
            self.article.text = text
        else:
            self.article.text = ""

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('title')
        if title_tag:
            self.article.title = title_tag.get_text(strip=True)
        else:
            self.article.title = "NOT FOUND"

        author = None
        meta_author = article_soup.find('meta', attrs={'name': 'author'})
        if meta_author and meta_author.get('content'):
            author = meta_author['content'].strip()
        else:
            author_div = article_soup.find('div', class_='author')
            if author_div:
                author = author_div.get_text(strip=True)
        if author:
            self.article.author = [author]
        else:
            self.article.author = ["NOT FOUND"]

    def unify_date_format(self, _: str) -> datetime.datetime:
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
        if response.status_code != 200:
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
    path = pathlib.Path(base_path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    config = Config(CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)

    crawler = Crawler(config)
    crawler.find_articles()
    article_urls = crawler.urls

    for idx, url in enumerate(article_urls, start=1):
        parser = HTMLParser(url, idx, config)
        article = parser.parse()
        if article and article.text:
            to_raw(article)
            to_meta(article)
            print(f"Saved article {idx}: {url}")

    print(f"Done. {len(article_urls)} articles saved.")

if __name__ == "__main__":
    main()
