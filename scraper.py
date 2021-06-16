import scrapy
import json
import datetime
import pytz
import urllib.parse
from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from scrapy.signalmanager import dispatcher


def query_input(query='https://shopee.co.id/lapak_laptop'):
    username = query.replace("https://shopee.co.id/", "").replace("/", "")
    return username


class ShopeeSpider(scrapy.Spider):
    # spider name
    name = 'shopee_spider'
    allowed_domains = ['shopee.co.id']

    # comment if you want run script standalone
    start_url = ''

    def __init__(self, url_query='', **kwargs):  # The query variable will have the input URL.
        self.username = query_input(url_query)  # get username from url_query
        self.start_url = 'https://shopee.co.id/api/v4/shop/get_shop_detail?username={}'.format(self.username)
        super().__init__(**kwargs)

    # base URL - for standalone
    # keyword = query_input()
    # start_url = 'https://shopee.co.id/api/v4/shop/get_shop_detail?username={}'.format('adidasindonesia')

    # custom headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36',
        'Referer': 'https://shopee.co.id/',
    }

    # custom settings
    custom_settings = {
        # uncomment below settings to slow down the scraper
        # 'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'DOWNLOAD_DELAY': 2,
        # 'USER_AGENT': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36',
        'DEFAULT_REQUEST_HEADERS': {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36',
            'Referer': 'https://shopee.co.id/',
        },
        # 'FEEDS': {'output/%(username)s_%(date)s.json': {
        #             'format': 'json',
        #         },
        # }

    }

    def start_requests(self):
        yield scrapy.Request(url=self.start_url, callback=self.parse)

    def parse(self, response):
        jsonresponse = json.loads(response.body.decode('utf-8'))
        shop_id = jsonresponse['data']['shopid']
        shop_name = jsonresponse['data']['name']
        number_of_products = jsonresponse['data']['item_count']
        shop_description = jsonresponse['data']['description']
        profile_image = 'https://cf.shopee.co.id/file/' + jsonresponse['data']['account']['portrait']
        if number_of_products > 30:
            limit = 100  # max 100
        else:
            limit = 30

        # define limit from number of products
        product_url = 'https://shopee.co.id/api/v4/search/search_items?by=pop&limit={}&match_id={}&newest=0&order=desc&page_type=shop&scenario=PAGE_OTHERS&version=2'.format(
            limit, shop_id)

        yield scrapy.Request(product_url,
                             headers=self.headers,
                             callback=self.parse_product,
                             meta={'shop_id': shop_id,
                                   'shop_name': shop_name,
                                   'number_of_products': number_of_products,
                                   'shop_description': shop_description,
                                   'profile_image': profile_image,
                                   })

    def parse_product(self, response):
        jsonresponse = json.loads(response.body.decode('utf-8'))
        for item in jsonresponse['items']:
            item_id = item['item_basic']['itemid']
            product_name = item['item_basic']['name']
            price = item['item_basic']['price']
            catid = item['item_basic']['catid']

            product_images = []
            for image in item['item_basic']['images']:
                product_img_url = 'https://cf.shopee.co.id/file/' + image
                product_images.append(product_img_url)

            yield {'shop_id': response.meta['shop_id'],
                   'shop_name': response.meta['shop_name'],
                   'number_of_products': response.meta['number_of_products'],
                   'shop_description': response.meta['shop_description'],
                   'profile_image': response.meta['profile_image'],
                   'item_id': item_id,
                   'category_id': catid,
                   'product_name': product_name,
                   'price': int(price / 100000),
                   'product_images': ", ".join(product_images),
                   }


# main driver
# uncomment if you run this script standalone
# if __name__ == '__main__':
#     # run spider
#     process = CrawlerProcess()
#     process.crawl(ShopeeSpider)
#     # process.crawl(ShopeeSpider, start_url='https://shopee.co.id/api/v4/shop/get_shop_detail?username=lapak_laptop')
#     process.start()
