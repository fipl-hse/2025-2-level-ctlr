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
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Raised when seed URL does not match standard pattern 'https?://(www.)?'
    """

class NumberOfArticlesOutOfRangeError(Exception):
    """
    Raised when total number of articles is out of range from 1 to 150
    """

class IncorrectNumberOfArticlesError(Exception):
    """
    Raised when total number of articles to parse is not integer or less than 0
    """

class IncorrectHeadersError(Exception):
    """
    Raised when headers are not in a form of dictionary
    """

class IncorrectEncodingError(Exception):
    """
    Raied when encoding is not specified as a string
    """

class IncorrectTimeoutError(Exception):
    """
    Raised when timeout value is not a positive integer that less than 60
    """

class IncorrectVerifyError(Exception):
    """
    Raised when verify certificate and headless mode values are not True or False
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
        config_dto = self._extract_config_content()
        self._validate_config_content()

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
        with open(self.path_to_config, encoding="utf-8") as config_data:
            self._config = ConfigDTO(**json.load(config_data))
        return self._config

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config = self._config

        if not isinstance(config.seed_urls, list) or not config.seed_urls:
            raise IncorrectSeedURLError(
                "Seed URLs must be a list of strings"
            )

        for url in config.seed_urls:
            if not isinstance(url, str) or not re.match(r"https?://(www.)?", url):
                raise IncorrectSeedURLError(
                    "Seed URL does not match standard pattern 'https?://(www.)?'"
                )

        if not isinstance(config.total_articles, int) or config.total_articles <= 0:
            raise IncorrectNumberOfArticlesError(
                "Total number of articles to parse is not integer or less than 0"
            )

        if config.total_articles < 1 or config.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError(
                "Total number of articles is out of range from 1 to 150"
            )

        if not isinstance(config.headers, dict):
            raise IncorrectHeadersError(
                "Headers are not in a form of dictionary"
            )

        if not isinstance(config.encoding, str):
            raise IncorrectEncodingError(
                "Encoding is not specified as a string"
            )

        if not isinstance(config.timeout, int) or config.timeout < 0 or config.timeout >= 60:
            raise IncorrectTimeoutError(
                "Timeout value is not a positive integer that less than 60"
            )

        if not isinstance(config.should_verify_certificate, bool) \
        or not isinstance(config.headless_mode, bool):
            raise IncorrectVerifyError(
                "Verify certificate and headless mode values are not True or False"
            )


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

    def set_seed_urls(self, seed_urls: list[str]) -> None:
        """
        Set seed urls to parse.

        Args:
            seed_urls (list[str]): New seed urls
        """
        self._seed_urls = seed_urls


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
        url=url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate(),
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
        url = article_bs.get("href")
        return "" if not isinstance(url, str) or not url else url

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

            soup = BeautifulSoup(response.text, features="lxml")
            parsed_seed = urlparse(seed_url)

            for tag in soup.find_all(["a"]):
                if len(self.urls) > self._config.get_num_articles():
                    return

                if not isinstance(tag, Tag):
                    continue

                extracted_url = self._extract_url(tag)
                if not extracted_url:
                    continue

                if not re.match("https?://(www.)?", extracted_url):
                    extracted_url = urlunparse(
                        (
                            parsed_seed.scheme,
                            parsed_seed.netloc,
                            extracted_url,
                            None,
                            None,
                            None
                        )
                    )
                else:
                    if parsed_seed.netloc != urlparse(extracted_url).netloc:
                        continue

                if extracted_url not in self.urls:
                    self.urls.append(extracted_url)

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

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """
        seed_urls_max_size = 3
        visited = set()
        queue = set()

        path = ASSETS_PATH / "RecursiveCrawlerState.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                current_state = json.load(f)
            visited = set(current_state.get("visited", []))
            queue = set(current_state.get("queue", []))
        else:
            queue = queue.union(set(self.get_search_urls()))

        self.urls = list(visited.union(queue))

        def _safe_current_state() -> None:
            nonlocal visited
            nonlocal queue
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "visited": list(visited),
                    "queue": list(queue)
                     },
                     f
                )

        while queue:
            if len(self.urls) > self._config.get_num_articles():
                break
            self._config.set_seed_urls([queue.pop() for _ in range(seed_urls_max_size) if queue])
            super().find_articles()
            visited = visited.union(self.get_search_urls())
            queue = queue.union({url for url in self.urls if url not in visited})
            _safe_current_state()

        _safe_current_state()

    # def find_articles_b(self) -> None:
    #     """
    #     Find number of article urls requested.
    #     """
    #     checkpoint_size = 2
    #     queue = []
    #     visited = set()
    #     path = ASSETS_PATH / "RecursiveCrawlerState.json"
    #     if path.exists():
    #         with open(path, encoding="utf-8") as f:
    #             current_state = json.load(f)
    #         visited = set(current_state["visited"])
    #         self._config._seed_urls = current_state["queue"]
    #         queue = current_state
    #     else:
    #         queue.extend(self.get_search_urls())

    #     def _safe_current_state():
    #         nonlocal visited
    #         nonlocal queue
    #         with open(path, "w", encoding="utf-8") as f:
    #             json.dump({
    #                 "visited": list(visited),
    #                 "queue": queue
    #                  },
    #                  f
    #             )

    #     for seed_url in self.get_search_urls():
    #         try:
    #             response = make_request(seed_url, self._config)
    #         except requests.exceptions.RequestException:
    #             continue

    #         if not response.ok:
    #             continue

    #         soup = BeautifulSoup(response.text, features="lxml")
    #         parsed_seed = urlparse(seed_url)
    #         tags = soup.find_all(["a"])
    #         if not tags:
    #             continue
    #         for tag in tags:
    #             if len(visited) > self._config.get_num_articles():
    #                 self.urls = list(visited)
    #                 return
    #             if len(visited) % checkpoint_size == 0:
    #                 _safe_current_state()

    #             if not isinstance(tag, Tag):
    #                 continue

    #             extracted_url = self._extract_url(tag)
    #             if not extracted_url:
    #                 continue

    #             if not re.match("https?://(www.)?", extracted_url):
    #                 extracted_url = urlunparse(
    #                     (
    #                         parsed_seed.scheme,
    #                         parsed_seed.netloc,
    #                         extracted_url,
    #                         None,
    #                         None,
    #                         None
    #                     )
    #                 )
    #             elif parsed_seed.netloc != urlparse(extracted_url).netloc:
    #                 continue

    #             if extracted_url not in visited:
    #                 visited.add(extracted_url)
    #         queue.remove(seed_url)

    #     _safe_current_state()
    #     self.find_articles()

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
        self.article = Article(full_url, article_id)
        self._config = config

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        articles = article_soup.find_all("article", class_="type-post")
        if not articles:
            return

        all_text = []
        for article in articles:
            tags = article.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote"])

            for tag in tags:
                tag_classes = tag.get("class")
                if tag.name == "p" and tag_classes and "has-medium-font-size" in tag_classes:
                    continue

                text = tag.get_text(strip=True)
                if not text:
                    continue
                all_text.append(text)

        self.article.text = "\n".join(all_text)


    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        self.article.article_id = self.article_id

        title = article_soup.find("title")
        if title and (title_content := title.get_text()):
            self.article.title = title_content

        author_tags = article_soup.find_all("meta", {"name": "author"})
        author_list = []
        for tag in author_tags:
            if not isinstance(tag, Tag):
                continue
            if (author_content := tag.get("content")):
                author_list.append(author_content)
        self.article.author = author_list if author_list else ["NOT FOUND"]

        date = article_soup.find("meta", {"property": "article:published_time"})
        if isinstance(date, Tag) and (date_content := date.get("content")):
            self.article.date = self.unify_date_format(str(date_content))
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
        return datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        response = make_request(self.full_url, self._config)
        if not response.ok:
            return False

        soup = BeautifulSoup(response.text, features="lxml")
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

    if pathlib.Path.exists(base_path):
        shutil.rmtree(base_path)

    base_path.mkdir(parents=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    prepare_environment(ASSETS_PATH)

    config = Config(CRAWLER_CONFIG_PATH)
    crawler = Crawler(config)
    crawler.find_articles()
    print(len(crawler.urls))
    for article_id, article_url in enumerate(crawler.urls, start=1):
        parser = HTMLParser(article_url, article_id, config)
        parsed_article = parser.parse()
        if isinstance(parsed_article, Article):
            to_raw(parsed_article)
            to_meta(parsed_article)

def main2() -> None:
    """
    Entrypoint for recursivescraper module.
    """
    if not ASSETS_PATH.exists():
        prepare_environment(ASSETS_PATH)

    config = Config(CRAWLER_CONFIG_PATH)
    # config._num_articles = 1500
    crawler = CrawlerRecursive(config)
    crawler.find_articles()
    print(len(crawler.urls))


if __name__ == "__main__":
    main()
