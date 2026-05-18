"""
Crawler implementation.
"""

import datetime
import json
import pathlib
import re
import shutil
from typing import Union

import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """Exception raised when seed URL is unusual"""

class IncorrectNumberOfArticlesError(Exception):
    """Exception raised when number of articles to parse is not int or < 0"""

class NumberOfArticlesOutOfRangeError(Exception):
    """Exception raised when number of articles to parse is out of range from 1 to 150"""

class IncorrectHeadersError(Exception):
    """Exception raised when Headers are not a dictionary"""

class IncorrectEncodingError(Exception):
    """Exception raised when Encoding is not a string"""

class IncorrectTimeoutError(Exception):
    """Exception raised when Timeout is not a positive int less than 60"""

class IncorrectVerifyError(Exception):
    """Exception raised when Verify Certificate is not a bool"""


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
        config_dto = self._extract_config_content()
        self._validate_config_content(config_dto)
        
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
        with open(self.path_to_config, 'r', encoding='utf-8') as file:
            config_data = json.load(file)

        return ConfigDTO(
            seed_urls=config_data.get('seed_urls', []),
            total_articles_to_find_and_parse=config_data.get('total_articles_to_find_and_parse', 0),
            headers=config_data.get('headers', {}),
            encoding=config_data.get('encoding', 'utf-8'),
            timeout=config_data.get('timeout', 30),
            should_verify_certificate=config_data.get('should_verify_certificate', True),
            headless_mode=config_data.get('headless_mode', False)
        )

    def _validate_config_content(self, config_dto: ConfigDTO) -> None:
        """
        Ensure configuration parameters are not corrupt.
        
        Args:
            config_dto (ConfigDTO): Configuration data to validate
        """
        if not isinstance(config_dto.seed_urls, list):
            raise IncorrectSeedURLError()
        
        if not config_dto.seed_urls:
            raise IncorrectSeedURLError()

        url_pattern = r'https?://(www\.)?.*'
        for url in config_dto.seed_urls:
            if not isinstance(url, str):
                raise IncorrectSeedURLError()
            if not re.match(url_pattern, url):
                raise IncorrectSeedURLError()


        if not isinstance(config_dto.total_articles, int):
            raise IncorrectNumberOfArticlesError()
        
        if config_dto.total_articles <= 0:
            raise IncorrectNumberOfArticlesError()
        
        if config_dto.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError()
        
        if not isinstance(config_dto.headers, dict):
            raise IncorrectHeadersError()
        
        if not isinstance(config_dto.encoding, str):
            raise IncorrectEncodingError()
        
        if not isinstance(config_dto.timeout, int):
            raise IncorrectTimeoutError()
        if not (0 < config_dto.timeout <= 60):
            raise IncorrectTimeoutError()
        
        if not isinstance(config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError()
        
        if not isinstance(config_dto.headless_mode, bool):
            raise IncorrectVerifyError()

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
        self.urls: list[str] = []

    def _extract_url(self, article_bs: BeautifulSoup) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.BeautifulSoup): BeautifulSoup instance of the page

        Returns:
            list[str]: List of urls from HTML
        """
        href = article_bs.get('href')
    
        if href.startswith('/'):
            full_url = f"https://samlib.ru{href}"
        elif not href.startswith('http'):
            full_url = f"https://samlib.ru/{href}"
        else:
            full_url = href
    
        return full_url

    def find_articles(self) -> None:
        """
        Find articles.
        """
        seed_urls = self.config.get_seed_urls()
        num_articles_needed = self.config.get_num_articles()

        for seed_url in seed_urls:
            if len(self.urls) >= num_articles_needed:
                break

            try:
                response = make_request(seed_url, self.config)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'lxml')

                    links = soup.find_all('a', href=True)
                    for link in links:
                        href = link.get('href')
                        if href and href.endswith('.shtml'):
                            full_url = self._extract_url(link)
                            if full_url not in self.urls and len(self.urls) < num_articles_needed:
                                self.urls.append(full_url)

            except RequestException:
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
        text_content = ''
        dd_tags = article_soup.find_all('dd') # кажется, что на этом сайте все тексты находятся в dd тегах
        pre_tags = article_soup.find_all('pre')

        if dd_tags:
            for dd in dd_tags:
                dd_text = dd.get_text(separator='\n', strip=True)
                if len(dd_text) > 200:
                    text_content += dd_text + '\n'
                    break
        
        if not text_content.strip():
            if pre_tags:
                for pre in pre_tags:
                    text_content += pre.get_text(strip=True) + '\n'
        
        if not text_content.strip():
            text_content = article_soup.get_text(separator='\n', strip=True)
                    
        self.article.text = text_content.strip()

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """

        title_tag = article_soup.find('title')

        if title_tag:
            full_title = title_tag.get_text(strip=True)
            if '. ' in full_title:
                parts = full_title.split('. ', 1)  
                self.article.author = [parts[0]]
                self.article.title = parts[1]       
            else:
                self.article.title = full_title
                self.article.author = ['NOT FOUND']
    
    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """

    def parse(self) -> Union[Article, bool]:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            if response.status_code != 200:
                return False

            article_soup = BeautifulSoup(response.text, 'lxml')
            self._fill_article_with_text(article_soup)
            self._fill_article_with_meta_information(article_soup)
            
            return self.article
        except Exception:
            return False


def prepare_environment(base_path: Union[pathlib.Path, str]) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    base_path = pathlib.Path(base_path)
    
    if base_path.exists():
        shutil.rmtree(base_path)

    base_path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)

    prepare_environment(ASSETS_PATH)

    crawler = Crawler(config=configuration)
    crawler.find_articles()

    article_urls = crawler.urls
    for i, url in enumerate(article_urls, 1):
        parser = HTMLParser(full_url=url, article_id=i, config=configuration)
        article = parser.parse()

        if article:
            to_raw(article)
            to_meta(article)

if __name__ == "__main__":
    main()
