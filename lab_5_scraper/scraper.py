"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes,
# pylint: disable=unused-import, undefined-variable, unused-argument

import datetime
import json
import pathlib
import re
import shutil

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
        with open(self.path_to_config, 'r', encoding='utf-8') as f:
            return ConfigDTO(**json.load(f))

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config_dto = self._extract_config_content()
        if not isinstance(config_dto.seed_urls, list) or not config_dto.seed_urls:
            raise IncorrectSeedURLError("Seed URLs must be a non-empty list.")
        url_pattern = re.compile(r"https?://(www\.)?")
        for url in config_dto.seed_urls:
            if not isinstance(url, str) or not url_pattern.match(url):
                raise IncorrectSeedURLError("Seed URL does not match standard pattern.")
        if (not isinstance(config_dto.total_articles, int) or
            isinstance(config_dto.total_articles, bool)):
            raise IncorrectNumberOfArticlesError("Total articles must be an integer.")
        if config_dto.total_articles <= 0:
            raise IncorrectNumberOfArticlesError("Total articles must be greater than 0.")
        if not 1 <= config_dto.total_articles <= 150:
            raise NumberOfArticlesOutOfRangeError("Total articles must be between 1 and 150.")
        if not isinstance(config_dto.headers, dict):
            raise IncorrectHeadersError("Headers must be a dictionary.")
        if not isinstance(config_dto.encoding, str):
            raise IncorrectEncodingError("Encoding must be specified as a string.")
        if not isinstance(config_dto.timeout, int) or isinstance(config_dto.timeout, bool):
            raise IncorrectTimeoutError("Timeout must be an integer.")
        if not 0 < config_dto.timeout < 60:
            raise IncorrectTimeoutError("Timeout must be a positive integer less than 60.")
        if not isinstance(config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError("Verify certificate value must be True or False.")
        if not isinstance(config_dto.headless_mode, bool):
            raise IncorrectVerifyError("Headless mode value must be True or False.")

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

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = article_bs.get("href", "")
        if not href:
            return ""

        href_str = str(href)

        if href_str.startswith("http"):
            return href_str

        if href_str.startswith("/"):
            href_str = href_str[1:]

        return "https://carsson.ru/" + href_str


    def find_articles(self) -> None:
        """
        Find articles.
        """
        needed = self.config.get_num_articles()
        seeds_to_visit = list(self.config.get_seed_urls())
        visited_seeds = set()

        blacklisted_keywords = [
            'karta-sajta', 'contacts', 'category', 'tag', 'author',
            'privacy', 'advertisement', 'about', 'plugins', 'interesnoe',
            'proza', 'stihi', 'novosti'
        ]

        for seed_url in seeds_to_visit:
            if len(self.urls) >= needed:
                break
            if seed_url in visited_seeds:
                continue
            visited_seeds.add(seed_url)

            response = make_request(seed_url, self.config)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.content, 'html.parser')

            for link in soup.find_all('a'):
                href = link.get("href", "")
                if not href:
                    continue

                article_url = self._extract_url(link)
                if not article_url or not article_url.startswith("https://carsson.ru/"):
                    continue

                if "/page/" in article_url:
                    if article_url not in visited_seeds and article_url not in seeds_to_visit:
                        seeds_to_visit.append(article_url)
                    continue

                if article_url in ("https://carsson.ru", "https://carsson.ru/") or \
                        any(word in article_url.lower() for word in blacklisted_keywords):
                    continue

                if link.find_parent(['h1', 'h2', 'article']) and article_url not in self.urls:
                    if len(self.urls) < needed:
                        self.urls.append(article_url)


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
        self.start_url = self.config.get_seed_urls()[0]

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
        self.article = Article(full_url, article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        paragraphs = article_soup.find_all('p')
        text_blocks = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]

        final_text = ' '.join(text_blocks)
        self.article.text = final_text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('h1', class_='entry-title')
        if not title_tag:
            title_tag = article_soup.find('h1')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if ':' in title_text:
                title_text = title_text.split(':')[0].strip()
            self.article.title = title_text
        else:
            self.article.title = "Untitled"
        self.article.author = ['NOT FOUND']
        self.article.topics = []

        time_tag = article_soup.find('time', class_='entry-date')
        date_str = ""

        if time_tag and time_tag.get_text():
            raw_text = time_tag.get_text(strip=True)
            date_match = re.search(r"\b\d{2}\.\d{2}\.\d{4}\b", raw_text)
            if date_match:
                date_str = date_match.group(0)

        if not date_str:
            date_pattern = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")
            date_match = date_pattern.search(article_soup.get_text())
            if date_match:
                date_str = date_match.group(0)

        if date_str:
            self.article.date = self.unify_date_format(date_str)
        else:
            self.article.date = datetime.datetime.now()

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        clean_date = date_str.strip()
        day, month, year = map(int, clean_date.split('.'))
        return datetime.datetime(year, month, day)

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        response = make_request(self.full_url, self.config)
        if not response or response.status_code != 200:
            return self.article

        soup = BeautifulSoup(response.text, 'html.parser')
        self._fill_article_with_meta_information(soup)
        self._fill_article_with_text(soup)
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
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config=configuration)
    crawler.find_articles()
    for i, fullurl in enumerate(crawler.urls):
        parser = HTMLParser(full_url=fullurl, article_id=i+1, config=configuration)
        article = parser.parse()
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)


if __name__ == "__main__":
    main()
