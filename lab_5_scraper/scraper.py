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

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO


class IncorrectSeedURLError(Exception):
    """Raised when seed URLs are invalid."""


class NumberOfArticlesOutOfRangeError(Exception):
    """Raised when number of articles is out of range 1-150."""


class IncorrectNumberOfArticlesError(Exception):
    """Raised when number of articles is not a positive integer."""


class IncorrectHeadersError(Exception):
    """Raised when headers are not a valid dictionary."""


class IncorrectEncodingError(Exception):
    """Raised when encoding is not a string."""


class IncorrectTimeoutError(Exception):
    """Raised when timeout is not a valid integer in range."""


class IncorrectVerifyError(Exception):
    """Raised when verify certificate or headless mode is not boolean."""


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
        self._validate_config_content()
        config_dto = self._extract_config_content()
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
            seed_urls=config_data['seed_urls'],
            total_articles_to_find_and_parse=config_data['total_articles_to_find_and_parse'],
            headers=config_data['headers'],
            encoding=config_data['encoding'],
            timeout=config_data['timeout'],
            should_verify_certificate=config_data['should_verify_certificate'],
            headless_mode=config_data['headless_mode']
        )


    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as file:
            config_data = json.load(file)

        seed_urls = config_data.get('seed_urls')
        if not isinstance(seed_urls, list) or not seed_urls:
            raise IncorrectSeedURLError('seed_urls must be a non-empty list.')
        for url in seed_urls:
            if not isinstance(url, str) or not re.match(r'https?://', url):
                raise IncorrectSeedURLError(f'Invalid seed URL: {url}')

        num_articles = config_data.get('total_articles_to_find_and_parse')
        if isinstance(num_articles, bool) or not isinstance(num_articles, int) or num_articles <= 0:
            raise IncorrectNumberOfArticlesError('total_articles must be a positive integer.')
        if num_articles > 150:
            raise NumberOfArticlesOutOfRangeError('total_articles must be <= 150.')

        headers = config_data.get('headers')
        if not isinstance(headers, dict):
            raise IncorrectHeadersError('headers must be a dictionary.')
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise IncorrectHeadersError('headers keys and values must be strings.')

        encoding = config_data.get('encoding')
        if not isinstance(encoding, str):
            raise IncorrectEncodingError('encoding must be a string.')

        timeout = config_data.get('timeout')
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0 or timeout > 60:
            raise IncorrectTimeoutError('timeout must be an integer between 1 and 60.')

        should_verify = config_data.get('should_verify_certificate')
        if not isinstance(should_verify, bool):
            raise IncorrectVerifyError('should_verify_certificate must be True or False.')

        headless = config_data.get('headless_mode')
        if not isinstance(headless, bool):
            raise IncorrectVerifyError('headless_mode must be True or False.')

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
        verify=config.get_verify_certificate(),
    )
    return response


class Crawler:
    """
    Crawler implementation.
    """
    url_pattern: re.Pattern | str = re.compile(r'https://eveszenary\.ru/(?!page/|category/|tag/|feed/|wp-|events/?$|privacy-policy/?$|#)[^/]+/$')

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
        return href if isinstance(href, str) else ""
        

    def find_articles(self) -> None:
        """
        Find articles.
        """
        seen: set[str] = set(self.urls)
        num_needed = self.config.get_num_articles()
        max_pages = 50

        for seed_url in self.config.get_seed_urls():
            page = 1
            while len(self.urls) < num_needed and page <= max_pages:
                paginated_url = seed_url if page == 1 else f"{seed_url.rstrip('/')}/page/{page}/"
                try:
                    response = make_request(paginated_url, self.config)
                    if response.status_code != 200:
                        break
                    soup = BeautifulSoup(response.content, 'html.parser')
                    found_new = False
                    for link_tag in soup.find_all('a', href=True):
                        url = self._extract_url(link_tag)
                        if re.match(self.url_pattern, url) and url not in seen:
                            seen.add(url)
                            self.urls.append(url)
                            found_new = True
                        if len(self.urls) >= num_needed:
                            return
                    if not found_new:
                        break
                    page += 1
                except Exception:  # pylint: disable=broad-except
                    break


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
        content_div = (
            article_soup.find('div', class_='entry-content')
            or article_soup.find('div', class_='post-content')
            or article_soup.find('article')
        )
        if content_div:
            paragraphs = content_div.find_all(['p', 'strong', 'em'])
            text_parts = [tag.get_text(separator=' ', strip=True) for tag in paragraphs if tag.get_text(strip=True)]
            self.article.text = '\n'.join(text_parts) if text_parts else content_div.get_text(strip=True)
        else:
            body = article_soup.find('body')
            self.article.text = body.get_text(separator='\n', strip=True) if body else ''

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('h1', class_='entry-title') or article_soup.find('h1')
        if title_tag:
            self.article.title = title_tag.get_text(strip=True)
        else:
            page_title = article_soup.find('title')
            self.article.title = page_title.get_text(strip=True).split('/')[0].strip() if page_title else ''

        # Author
        author_tag = (
            article_soup.find('span', class_='author')
            or article_soup.find('a', rel='author')
            or article_soup.find(class_='author')
        )
        if author_tag:
            self.article.author = [author_tag.get_text(strip=True)]
        else:
            meta_author = article_soup.find('meta', attrs={'name': 'author'})
            if meta_author and meta_author.get('content'):
                self.article.author = [meta_author['content']]
            else:
                self.article.author = ['NOT FOUND']

        # Date
        date_tag = (
            article_soup.find('time', class_='entry-date')
            or article_soup.find('time', class_='published')
            or article_soup.find('time')
        )
        if date_tag and date_tag.get('datetime'):
            self.article.date = self.unify_date_format(date_tag['datetime'])
        else:
            meta_date = article_soup.find('meta', attrs={'property': 'article:published_time'})
            if meta_date and meta_date.get('content'):
                self.article.date = self.unify_date_format(meta_date['content'])
            else:
                self.article.date = datetime.datetime(2000, 1, 1, 0, 0, 0)

        # Topics
        topics: list[str] = []
        tags_container = (
            article_soup.find('div', class_='entry-tags')
            or article_soup.find('div', class_='post-tags')
            or article_soup.find('span', class_='tags-links')
        )
        if tags_container:
            for tag_link in tags_container.find_all('a'):
                topic = tag_link.get_text(strip=True)
                if topic:
                    topics.append(topic)
        if not topics:
            for cat_link in article_soup.find_all('a', rel='tag'):
                topic = cat_link.get_text(strip=True)
                if topic:
                    topics.append(topic)
        self.article.topics = topics

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                dt = datetime.datetime.strptime(date_str[:19], fmt[:len(fmt)])
                return dt.replace(tzinfo=None)
            except ValueError:
                continue
        clean = re.sub(r'[+\-]\d{2}:\d{2}$', '', date_str).strip()
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.datetime.strptime(clean, fmt)
            except ValueError:
                continue
        return datetime.datetime(2000, 1, 1, 0, 0, 0)

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            if response.status_code != 200:
                return False
        except requests.RequestException:
            return False

        response.encoding = self.config.get_encoding()
        article_soup = BeautifulSoup(response.content, 'html.parser')
        self._fill_article_with_text(article_soup)
        self._fill_article_with_meta_information(article_soup)
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
    base_path.mkdir(parents=True, exist_ok=True)



def main() -> None:
    """
    Entrypoint for scraper module.
    """
    from core_utils.article.io import to_meta, to_raw
    from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH

    config = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)

    crawler = Crawler(config=config)
    crawler.find_articles()

    for article_id, url in enumerate(crawler.urls[:config.get_num_articles()], start=1):
        parser = HTMLParser(full_url=url, article_id=article_id, config=config)
        article = parser.parse()
        if isinstance(article, Article) and article.text:
            to_raw(article)
            to_meta(article)
            print(article.text)


if __name__ == "__main__":
    main()
