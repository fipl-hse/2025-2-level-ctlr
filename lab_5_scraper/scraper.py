"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
import shutil
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    "seed URL does not match standard pattern"
    pass
class NumberOfArticlesOutOfRangeError(Exception):
    "total number of articles is out of range from 1 to 150"
    pass
class IncorrectNumberOfArticlesError(Exception):
    "total number of articles to parse is not integer or less than 0"
    pass
class IncorrectHeadersError(Exception):
    "headers are not in a form of dictionary"
    pass
class IncorrectEncodingError(Exception):
    "encoding must be specified as a string"
    pass
class IncorrectTimeoutError(Exception):
    "timeout value must be a positive integer less than 60"
    pass
class IncorrectVerifyError(Exception):
    "verify certificate and headless mode values must either be 'True' or 'False'"
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
        self._config = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = self._config.seed_urls
        self._num_articles = self._config.total_articles
        self._headers = self._config.headers
        self._encoding = self._config.encoding
        self._timeout = self._config.timeout
        self._headless_mode = self._config.headless_mode
        self._should_verify_certificate = self._config.should_verify_certificate

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, "r", encoding = "utf-8") as f:
            data = json.load(f)
        return ConfigDTO(**data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        dto = self._config
        if not isinstance(dto.seed_urls, list):
            raise IncorrectSeedURLError()
        pattern = re.compile(r"https?://(www.)?")
        for url in dto.seed_urls:
            if not pattern.match(url):
                raise IncorrectSeedURLError()
        if (not isinstance(dto.total_articles, int)
                or dto.total_articles < 1):
            raise IncorrectNumberOfArticlesError()
        if dto.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError()
        if not isinstance(dto.headers, dict):
            raise IncorrectHeadersError()
        if not isinstance(dto.encoding, str):
            raise IncorrectEncodingError()
        if not isinstance(dto.timeout, int) or dto.timeout<=0 or dto.timeout>=60:
            raise IncorrectTimeoutError()
        if not isinstance(dto.headless_mode, bool) or not isinstance(dto.should_verify_certificate, bool):
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
        headers= config.get_headers(), 
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
        try:
            href = article_bs["href"]
        except KeyError:
            return ""
        if not href:
            return ""
        if href.startswith(('http://', 'https://')):
            return href
        return urljoin("https://rus-shake.ru", href)

    def find_articles(self) -> None:
        """
        Find articles.
        """
        seed_urls = self._config.get_seed_urls()
        number_of_articles = self._config.get_num_articles()
        for seed_url in seed_urls:
            if len(self.urls) >= number_of_articles:
                    return
            try:
                response = make_request(seed_url, self._config)
                soup = BeautifulSoup(response.text, features="lxml")
                base_path = seed_url.replace('https://rus-shake.ru', '')
                base_path = base_path[:base_path.rfind('/')] + '/'
                for tag in soup.find_all('a', href=True):
                    link = self._extract_url(tag)
                    if not link or link in self.urls:
                        continue
                    if base_path in link:
                        self.urls.append(link)
            except Exception:
                continue

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
        self.article_id = article_id
        self.config = config
        self.article = Article(url=full_url, article_id=article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        content_div = article_soup.find('div', class_='content')
        if content_div:
            paragraphs = content_div.find_all('p')
            texts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            list_items = content_div.find_all('li')
            for li in list_items:
                text = li.get_text(strip=True)
                if text:
                    texts.append(text)
            self.article.text = '\n\n'.join(texts)
        else:
            self.article.text = ""

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find("title")
        if title_tag:
            raw_title = title_tag.text.strip()
            if '|' in raw_title:
                self.article.title = raw_title.split('|')[-1].strip()
            else:
                self.article.title = raw_title
        else:
            self.article.title = "NO TITLE"

        author_tag = article_soup.find("meta", attrs={"name": "author"})
        if author_tag and author_tag.get("content"):
            self.article.author = [author_tag.get("content").strip()]
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

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            article_soup = BeautifulSoup(response.text, features="lxml")
            self._fill_article_with_text(article_soup)
            self._fill_article_with_meta_information(article_soup)
            return self.article
        except requests.RequestException:
            return False


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
    config = Config(CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config)
    crawler.find_articles()
    for id, url in enumerate(crawler.urls, 1):
        if id > config.get_num_articles():
            break
        parser = HTMLParser(full_url=url, article_id=id, config=config)
        article = parser.parse()
        if article:
            to_raw(article)
            to_meta(article)


if __name__ == "__main__":
    main()
