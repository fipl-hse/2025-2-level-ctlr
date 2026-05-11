"""
Crawler implementation.
"""

import datetime
import json
import pathlib
import re
import shutil

import requests
from bs4 import BeautifulSoup

from core_utils.article.article import Article
from core_utils.article.io import to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


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
        (self._seed_urls, self._total, self._headers, self._encoding,
         self._timeout, self._verify, self._headless) = self._validate_and_load()

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self._path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return ConfigDTO(**data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        dto = self._extract_config_content()

        seed_urls = dto.seed_urls
        total = dto.total_articles_to_find_and_parse
        headers = dto.headers
        encoding = dto.encoding
        timeout = dto.timeout
        verify = dto.should_verify_certificate
        headless = dto.headless_mode

        pattern = re.compile(r'https?://(www\.)?')
        for url in seed_urls:
            if not pattern.match(url):
                raise IncorrectSeedURLError(f"Invalid seed URL: {url}")

        if not isinstance(total, int) or total <= 0:
            raise IncorrectNumberOfArticlesError(
                "total_articles_to_find_and_parse must be positive")
        if not 1 <= total <= 150:
            raise NumberOfArticlesOutOfRangeError(
                "total_articles_to_find_and_parse must be between 1 and 150")

        if not isinstance(headers, dict):
            raise IncorrectHeadersError("Headers must be a dictionary")
        if not isinstance(encoding, str):
            raise IncorrectEncodingError("Encoding must be a string")
        if not isinstance(timeout, int) or timeout <= 0 or timeout > 60:
            raise IncorrectTimeoutError("Timeout must be integer between 1 and 60")
        if not isinstance(verify, bool):
            raise IncorrectVerifyError("should_verify_certificate must be boolean")
        if not isinstance(headless, bool):
            raise IncorrectVerifyError("headless_mode must be boolean")

        return seed_urls, total, headers, encoding, timeout, verify, headless

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
        return ""

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
        for elem in soup(['script', 'style', 'nav', 'header', 'footer']):
            elem.decompose()
        content = soup.find('pre')
        if not content:
            content = soup.find('div', class_='text')
        if not content:
            content = soup.find('body')
        if content:
            paragraphs = content.find_all(['p', 'pre', 'div'])
            if paragraphs:
                text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)
            else:
                text = content.get_text(strip=True)
            self.article.text = text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        pass

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
        if response.status_code != 200:
            return False
        soup = BeautifulSoup(response.text, 'html.parser')
        self._fill_article_with_text(soup)
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
            to_raw(article, ASSETS_PATH)
            print(f"Saved article {idx}")
        else:
            print(f"Failed to parse article {idx}")

if __name__ == "__main__":
    main()
