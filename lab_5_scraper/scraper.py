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
import random

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH
from core_utils.article.io import to_raw, to_meta

class IncorrectSeedURLError(Exception):
    'seed URL does not match standard pattern "https?://(www.)?"'

class NumberOfArticlesOutOfRangeError(Exception):
    'total number of articles is out of range (from 1 to 150)'

class IncorrectNumberOfArticlesError(Exception):
    'total number of articles to parse is not integer or less than 0'

class IncorrectHeadersError(Exception):
    'headers are not in a form of dictionary'

class IncorrectEncodingError(Exception):
    'encoding must be specified as a string'

class IncorrectTimeoutError(Exception):
    'timeout value must be a positive integer less than 60'

class IncorrectVerifyError(Exception):
    'verify certificate and headless mode values must either be True or False'


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
        config_content = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = config_content.seed_urls
        self._num_articles = config_content.total_articles
        self._headers = config_content.headers
        self._encoding = config_content.encoding
        self._timeout = config_content.timeout
        self._should_verify_certificate = config_content.should_verify_certificate

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """

        with open (self.path_to_config, 'r', encoding='utf-8') as file:
            config_data = json.load(file)
        return ConfigDTO(**config_data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        self.config_content = self._extract_config_content()

        if not isinstance(self.config_content.seed_urls, list):
            raise IncorrectSeedURLError('seed URLs must be a list')
        for url in self.config_content.seed_urls:
            if not isinstance(url, str) or not re.match(r"https?://(www.)?", url):
                raise IncorrectSeedURLError('seed URL does not match standard pattern "https?://(www.)?"')
        if (not isinstance(self.config_content.total_articles, int)
            or isinstance(self.config_content.total_articles, bool)
            or self.config_content.total_articles < 1):
            raise IncorrectNumberOfArticlesError('total number of articles to parse is not integer or less than 0')
        if self.config_content.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError('total number of articles is out of range (from 1 to 150)')
        if not isinstance(self.config_content.headers, dict):
            raise IncorrectHeadersError('headers are not in a form of dictionary')
        if not isinstance(self.config_content.encoding, str):
            raise IncorrectEncodingError('encoding must be specified as a string')
        if (not isinstance(self.config_content.timeout, int) 
            or self.config_content.timeout < 0 
            or self.config_content.timeout > 60):
            raise IncorrectTimeoutError('timeout value must be a positive integer less than 60')
        if (not isinstance(self.config_content.should_verify_certificate, bool) 
            or not isinstance(self.config_content.headless_mode, bool)):
            raise IncorrectVerifyError('verify certificate and headless mode values must either be True or False')


    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self.config_content.seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self.config_content.total_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self.config_content.headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self.config_content.encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self.config_content.timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self.config_content.should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self.config_content.headless_mode


def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """
    time.sleep(random.uniform(0.5, 3))
    response = requests.get(
        url = url,
        headers = config.get_headers(),
        timeout = config.get_timeout(),
        verify = config.get_verify_certificate()
    )
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
        self._config = config
        self.urls = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        url = article_bs.get('href')
        if not isinstance(url, str):
            return ''
        if url.startswith('http'):
            if 'burkin.rusf.ru' not in url:
                return ''
            return url
        return 'https://burkin.rusf.ru/' + url.lstrip('/')

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.get_search_urls():
            try:
                response = make_request(seed_url, self._config)
            except requests.exceptions.RequestException:
                continue
            if not response.ok:
                continue
            soup = BeautifulSoup(response.content, 'lxml')
            for link in soup.find_all('a', href=True):
                url = self._extract_url(link)
                if url and url not in self.urls:
                    self.urls.append(url)
                if len(self.urls) >= self._config.get_num_articles():
                    return
            time.sleep(random.uniform(0.5, 3.0))

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self._config.get_seed_urls()


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
        self.config = config
        self.article_id = article_id
        self.article = Article(url=full_url, article_id=article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        texts = []
        for tag in article_soup.find_all(['p', 'dt']):
            text = tag.get_text(strip=True)
            if text:
                texts.append(text)
        self.article.text = '\n'.join(texts)



    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('td', align='left')
        if title_tag:
            strong = title_tag.find('strong')
            self.article.title = strong.get_text(strip=True) if strong else 'NOT FOUND'
        else:
            self.article.title = 'NOT FOUND'
        
        author_tag = article_soup.find('a', href=re.compile(r'mailto:burkin'))
        if author_tag:
            author_text = author_tag.get_text(strip=True)
            if author_text and '@' not in author_text:
                self.article.author = [author_text]
            else:
                self.article.author = ['NOT FOUND']
        else:
            self.article.author = ['NOT FOUND']

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        response = make_request(self.full_url, self.config)
        if not response.ok:
            return False
        article_soup = BeautifulSoup(response.content, 'lxml')
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
    path.mkdir(parents=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    configuration = Config(CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(configuration)
    crawler.find_articles()
    for art_id, url in enumerate(crawler.urls, 1):
        parser = HTMLParser(url, art_id, configuration)
        article = parser.parse()
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)


if __name__ == "__main__":
    main()
