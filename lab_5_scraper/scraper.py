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
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Seed URL does not match standard pattern "https?://(www.)?
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
    Verify certificate and headless mode values must either be ``True`` or ``False``.
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
        self.config_content = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = self.config_content.seed_urls
        self._num_articles = self.config_content.total_articles
        self._headers = self.config_content.headers
        self._encoding = self.config_content.encoding
        self._timeout = self.config_content.timeout
        self._should_verify_certificate = self.config_content.should_verify_certificate
        self._headless_mode = self.config_content.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, encoding="utf-8") as file:
            config_data = json.load(file)
        configuration = ConfigDTO(**config_data)
        return configuration

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config_content = self._extract_config_content()
        if not isinstance(config_content.seed_urls, list):
            raise IncorrectSeedURLError()
        for seed_url in config_content.seed_urls:
            if not re.match("https?://(www.)?", seed_url, 0):
                raise IncorrectSeedURLError()
        num_articles = config_content.total_articles
        if not isinstance(num_articles, int):
            raise IncorrectNumberOfArticlesError()
        if num_articles <= 0:
            raise IncorrectNumberOfArticlesError()
        if num_articles < 1 or num_articles > 150:
            raise NumberOfArticlesOutOfRangeError()
        if not isinstance(config_content.headers, dict):
            raise IncorrectHeadersError()
        if not isinstance(config_content.encoding, str):
            raise IncorrectEncodingError()
        timeout = config_content.timeout
        if not isinstance(timeout, int) or timeout >= 60 or timeout < 0:
            raise IncorrectTimeoutError()
        if not (
            isinstance(config_content.should_verify_certificate, bool)
            and isinstance(config_content.headless_mode, bool)
            ):
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
    headers = config.get_headers()
    timeout = config.get_timeout()
    verify = config.get_verify_certificate()
    response = requests.get(url, headers=headers, timeout=timeout, verify=verify)
    # except requests.exceptions.Timeout:
    #     print("Timeout: Server didn't respond in 3s")
    # except requests.exceptions.RequestException as e:
    #     print(f"Request failed: {e}")
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
        relative_link = str(article_bs.get("href"))
        return relative_link

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.config.get_seed_urls():
            if len(self.urls) > self.config.get_num_articles():
                break
            response = make_request(seed_url, self.config)
            if response and response.status_code == 200:
                soup = BeautifulSoup(response.text)
                all_links = soup.find_all("a")
                for link_tag in all_links: #going through tags of links located in an html page
                    new_relative_url = self._extract_url(link_tag)
                    new_full_url = urljoin(seed_url, new_relative_url)
                    if (
                    '/item/' in new_full_url
                    and
                    new_full_url not in self.urls
                    ):
                        self.urls.append(new_full_url)
                    #time.sleep(1)

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

    # pylint: disable=useless-parent-delegation
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
        self.article = Article(full_url, article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        texts = []
        # Following is a complex algorythm to finally find all text in an article webpage
        content_div = article_soup.find("div", class_="itemFullText")
        if not content_div:
            content_div = article_soup.find("div", class_="article-content")
        if not content_div:
            content_div = article_soup.find("div", itemprop="articleBody")
        if content_div:
            for tag in content_div.find_all(["p", "blockquote", "div"]):
                text = tag.get_text(strip=True)
                if text:
                    texts.append(text)
        else:
            for tag in article_soup.find_all(["p", "blockquote"]):
                text = tag.get_text(strip=True)
                if text:
                    texts.append(text)
        self.article.text = " ".join(texts)

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        author_tag = article_soup.find("meta", attrs={"name": "author"})
        author_content = author_tag["content"] if author_tag else "NOT FOUND"
        self.article.author = author_content.split(", ")

        title_tag = article_soup.find("meta", attrs={"name": "og:title"})
        title_content = str(title_tag["content"] if title_tag else "NOT FOUND")
        self.article.title = title_content

        finding_date_tag = article_soup.find("div", class_="itemHeader")
        if finding_date_tag:
            date_tag = finding_date_tag.find("span", class_="itemDateCreated")
            if date_tag:
                date_str = date_tag.get_text()
                self.article.date = self.unify_date_format(date_str)
            else:
                self.article.date = datetime.datetime.now()
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
        # Example: "Вторник, 26 мая 2015 07:20"
        months_map = {
        'января': '01',
        'февраля': '02',
        'марта': '03',
        'апреля': '04',
        'мая': '05',
        'июня': '06',
        'июля': '07',
        'августа': '08',
        'сентября': '09',
        'октября': '10',
        'ноября': '11',
        'декабря': '12'
        }
        for gen, nom in months_map.items():
            date_str = date_str.replace(gen, nom)
        date_str = date_str.replace("\n", "").strip()
        coma_ind = date_str.find(",")
        date_str = date_str[coma_ind+2:]
        parsed_date = datetime.datetime.strptime(date_str, "%d %m %Y %H:%M")
        return parsed_date

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            #time.sleep(1)
            if response.status_code != 200:
                return False
            response.encoding = self.config.get_encoding()
            article_bs = BeautifulSoup(response.text, "html.parser")
            self._fill_article_with_text(article_bs)
            self._fill_article_with_meta_information(article_bs)
        except(requests.RequestException, AttributeError, KeyError, ValueError, TypeError):
            return False
        return self.article


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    if base_path.exists():
        shutil.rmtree(base_path)
    base_path.mkdir(parents=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    print(f"CONFIG TOTAL ARTICLES: {configuration.get_num_articles()}")
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config=configuration)
    crawler.find_articles()
    urls = crawler.urls
    article_urls = [url for url in urls if '/item/' in url]
    print(f"FOUND {len(article_urls)} article URLs")
    article_urls = article_urls[:configuration.get_num_articles()]
    print(f"WILL PROCESS {len(article_urls)} articles")
    i = 1
    for full_url in article_urls:
        #time.sleep()
        print(f"Processing {i}: {full_url}")
        parser = HTMLParser(full_url=full_url, article_id=i, config=configuration)
        article = parser.parse()
        if isinstance(article, Article) and article.text and len(article.text.strip()) >= 50:
            to_raw(article)
            to_meta(article)
            i += 1

if __name__ == "__main__":
    main()
