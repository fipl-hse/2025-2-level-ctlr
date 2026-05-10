"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import random
import re
import shutil
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Seed URL does not match standard pattern.
    """

class NumberOfArticlesOutOfRangeError(Exception):
    """
    Total number of articles is out of range from 1 to 150.
    """

class IncorrectNumberOfArticlesError(Exception):
    """
    Total number of articles to parse is not integer or less than 0.
    """

class IncorrectHeadersError(Exception):
    """
    Headers are not in a form of dictionary.
    """

class IncorrectEncodingError(Exception):
    """
    Encoding must be specified as a string.
    """

class IncorrectTimeoutError(Exception):
    """
    Timeout value must be a positive integer less than 60.
    """

class IncorrectVerifyError(Exception):
    """
    Verify certificate and headless mode values must either be True or False.
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
        self._config = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = self._config.seed_urls
        self._num_articles = self._config.total_articles
        self._headers = self._config.headers
        self._encoding = self._config.encoding
        self._timeout = self._config.timeout
        self._should_verify_certificate = self._config.should_verify_certificate
        self._headless_mode = self._config.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, "r", encoding="utf-8") as file:
            data = json.load(file)
        return ConfigDTO(**data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        standard_pattern = re.compile(r"https?://(www\.)?")
        if not isinstance(self._config.seed_urls, list):
            raise IncorrectSeedURLError("Seed URLs must be a list of strings")
        for url in self._config.seed_urls:
            if not isinstance(url, str) or not standard_pattern.match(url):
                raise IncorrectSeedURLError("Seed URL does not match standard pattern")
        if not isinstance(self._config.total_articles, int):
            raise IncorrectNumberOfArticlesError("Total articles must be an integer")
        if self._config.total_articles < 1:
            raise IncorrectNumberOfArticlesError("Total articles must be at least 1")
        if self._config.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError("Total articles must not exceed 150")
        if not isinstance(self._config.headers, dict):
            raise IncorrectHeadersError("Headers must be a dictionary")
        if not isinstance(self._config.encoding, str):
            raise IncorrectEncodingError("Encoding must be a string")
        if not isinstance(self._config.timeout, int) or self._config.timeout <= 0 or self._config.timeout > 60:
            raise IncorrectTimeoutError("Timeout must be an integer between 1 and 60")
        if not isinstance(self._config.should_verify_certificate, bool):
            raise IncorrectVerifyError("should_verify_certificate must be a boolean")
        if not isinstance(self._config.headless_mode, bool):
            raise IncorrectVerifyError("headless_mode must be a boolean")


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
    time.sleep(random.uniform(0.5, 1))
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
        href = article_bs.get("href")
        if not href or not isinstance(href, str):
            return ""
        parsed = urlparse(href)
        if parsed.scheme in ('http', 'https'):
            return href
        base_url = self.config.get_seed_urls()[0]
        return urljoin(base_url, href)

    def find_articles(self) -> None:
        """
        Find articles.
        """
        article_pattern = re.compile(
            r'/(schedule|performances|persons)/(\d{3,4})/?$|/news/article/\d+/'
        )
        for seed_url in self.config.get_seed_urls():
            if len(self.urls) >= self.config.get_num_articles():
                return
            try:
                response = make_request(seed_url, self.config)
                if not response:
                    continue
                soup = BeautifulSoup(response.text, "lxml")
                for tag in soup.find_all("a"):
                    link = self._extract_url(tag)
                    if not link or link in self.urls:
                        continue
                    if article_pattern.search(link):
                        self.urls.append(link)
                    if len(self.urls) >= self.config.get_num_articles():
                        return
            except (requests.RequestException, AttributeError, ValueError):
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
        self.article = Article(url=self.full_url, article_id=self.article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        texts = []
        content_block = article_soup.find("div", class_="content content_1")
        if content_block:
            for p in content_block.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    texts.append(text)
        self.article.text = "\n\n".join(texts) if texts else ""

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title = article_soup.find("title")
        if title:
            self.article.title = title.text.strip()
        else:
            self.article.title = "NOT FOUND"
        author = article_soup.find("meta", attrs={"name": "author"})
        if author and author.get("content"):
            self.article.author = [author.get("content").strip()]
        else:
            self.article.author = ["NOT FOUND"]
        date_div = article_soup.find("div", class_="date_post")
        if date_div:
            date_text = date_div.get_text(strip=True)
            self.article.date = self.unify_date_format(date_text)
        else:
            self.article.date = datetime.datetime.now()
        keywords = article_soup.find("meta", {"name": "keywords"})
        if keywords and keywords.get("content"):
            self.article.topics = [k.strip() for k in keywords["content"].split(",")]
        else:
            self.article.topics = []

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        months = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
        'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
        'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
        date_str = date_str.replace(" г.", "")
        day, month_name, year = date_str.split()
        month = months[month_name]
        return datetime.datetime(int(year), month, int(day))

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        response = make_request(self.full_url, self.config)
        if not response:
            return False
        article_soup = BeautifulSoup(response.text, "lxml")
        self._fill_article_with_text(article_soup)
        self._fill_article_with_meta_information(article_soup)
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
    configuration = Config(CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(configuration)
    crawler.find_articles()
    for i, url in enumerate(crawler.urls, 1):
        if i > configuration.get_num_articles():
            break
        parser = HTMLParser(url, i, configuration)
        result = parser.parse()
        if isinstance(result, Article):
            to_raw(result)
            to_meta(result)


if __name__ == "__main__":
    main()
