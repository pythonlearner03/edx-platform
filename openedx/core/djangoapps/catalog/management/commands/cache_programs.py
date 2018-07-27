import logging
import sys

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.management import BaseCommand

from openedx.core.djangoapps.catalog.cache import (
    CREDIT_PATHWAY_CACHE_KEY_TPL,
    PROGRAM_CACHE_KEY_TPL,
    SITE_CREDIT_PATHWAY_IDS_CACHE_KEY_TPL,
    SITE_PROGRAM_UUIDS_CACHE_KEY_TPL
)
from openedx.core.djangoapps.catalog.models import CatalogIntegration
from openedx.core.djangoapps.catalog.utils import create_catalog_api_client

logger = logging.getLogger(__name__)
User = get_user_model()  # pylint: disable=invalid-name


class Command(BaseCommand):
    """Management command used to cache program data.

    This command requests every available program from the discovery
    service, writing each to its own cache entry with an indefinite expiration.
    It is meant to be run on a scheduled basis and should be the only code
    updating these cache entries.
    """
    help = "Rebuild the LMS' cache of program data."

    def handle(self, *args, **options):
        failure = False
        logger.info('populate-multitenant-programs switch is ON')

        catalog_integration = CatalogIntegration.current()
        username = catalog_integration.service_username

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            logger.error(
                'Failed to create API client. Service user {username} does not exist.'.format(username=username)
            )
            raise

        programs = {}
        pathways = {}
        for site in Site.objects.all():
            site_config = getattr(site, 'configuration', None)
            if site_config is None or not site_config.get_value('COURSE_CATALOG_API_URL'):
                logger.info('Skipping site {domain}. No configuration.'.format(domain=site.domain))
                cache.set(SITE_PROGRAM_UUIDS_CACHE_KEY_TPL.format(domain=site.domain), [], None)
                cache.set(SITE_CREDIT_PATHWAY_IDS_CACHE_KEY_TPL.format(domain=site.domain), [], None)
                continue

            client = create_catalog_api_client(user, site=site)
            uuids, program_uuids_failed = self.get_site_program_uuids(client, site)
            new_programs, program_details_failed = self.fetch_program_details(client, uuids)
            new_pathways, pathways_failed = self.get_pathways(client, site)
            new_pathways, new_programs, pathway_processing_failed = self.process_pathways(site, new_pathways,
                                                                                          new_programs)

            if program_uuids_failed or program_details_failed or pathways_failed or pathway_processing_failed:
                failure = True

            programs.update(new_programs)
            pathways.update(new_pathways)

            logger.info('Caching UUIDs for {total} programs for site {site_name}.'.format(
                total=len(uuids),
                site_name=site.domain,
            ))
            cache.set(SITE_PROGRAM_UUIDS_CACHE_KEY_TPL.format(domain=site.domain), uuids, None)

            pathway_ids = new_pathways.keys()
            logger.info('Caching ids for {total} credit pathways for site {site_name}.'.format(
                total=len(pathway_ids),
                site_name=site.domain,
            ))
            cache.set(SITE_CREDIT_PATHWAY_IDS_CACHE_KEY_TPL.format(domain=site.domain), pathway_ids, None)

        successful_programs = len(programs)
        logger.info('Caching details for {successful_programs} programs.'.format(
            successful_programs=successful_programs))
        cache.set_many(programs, None)

        successful_pathways = len(pathways)
        logger.info('Caching details for {successful_pathways} credit pathways.'.format(
            successful_pathways=successful_pathways))
        cache.set_many(pathways, None)

        if failure:
            # This will fail a Jenkins job running this command, letting site
            # operators know that there was a problem.
            sys.exit(1)

    def get_site_program_uuids(self, client, site):
        failure = False
        uuids = []
        try:
            querystring = {
                'exclude_utm': 1,
                'status': ('active', 'retired'),
                'uuids_only': 1,
            }

            logger.info('Requesting program UUIDs for {domain}.'.format(domain=site.domain))
            uuids = client.programs.get(**querystring)
        except:  # pylint: disable=bare-except
            logger.error('Failed to retrieve program UUIDs for site: {domain}.'.format(domain=site.domain))
            failure = True

        logger.info('Received {total} UUIDs for site {domain}'.format(
            total=len(uuids),
            domain=site.domain
        ))
        return uuids, failure

    def fetch_program_details(self, client, uuids):
        programs = {}
        failure = False
        for uuid in uuids:
            try:
                cache_key = PROGRAM_CACHE_KEY_TPL.format(uuid=uuid)
                logger.info('Requesting details for program {uuid}.'.format(uuid=uuid))
                program = client.programs(uuid).get(exclude_utm=1)
                # pathways get added in process_pathways
                program['pathway_ids'] = []
                programs[cache_key] = program
            except:  # pylint: disable=bare-except
                logger.exception('Failed to retrieve details for program {uuid}.'.format(uuid=uuid))
                failure = True
                continue
        return programs, failure

    def get_pathways(self, client, site):
        """
        Get all pathways for the current client
        """
        pathways = {}
        failure = False
        logger.info('Requesting credit pathways for {domain}.'.format(domain=site.domain))
        try:
            pathways = client.credit_pathways.get(exclude_utm=1)['results']
        except:  # pylint: disable=bare-except
            logger.error('Failed to retrieve credit pathways for site: {domain}.'.format(domain=site.domain))
            failure = True

        logger.info('Received {total} credit pathways for site {domain}'.format(
            total=len(pathways),
            domain=site.domain
        ))

        return pathways, failure

    def process_pathways(self, site, pathways, programs):
        """
        For each program, added references to each pathway it is a part of.
        For each pathway, replace the "programs" dict with "program_uuids",
        which only contains uuids (since program data is already cached)
        """
        processed_pathways = {}
        failure = False
        try:
            for pathway in pathways:
                pathway_id = pathway['id']
                pathway_cache_key = CREDIT_PATHWAY_CACHE_KEY_TPL.format(id=pathway_id)
                processed_pathways[pathway_cache_key] = pathway
                uuids = []

                for program in pathway['programs']:
                    program_uuid = program['uuid']
                    program_cache_key = PROGRAM_CACHE_KEY_TPL.format(uuid=program_uuid)
                    programs[program_cache_key]['pathway_ids'].append(pathway_id)
                    uuids.append(program_uuid)

                del pathway['programs']
                pathway['program_uuids'] = uuids
        except:  # pylint: disable=bare-except
            logger.error('Failed to process pathways for {domain}'.format(domain=site.domain))
            failure = True
        return processed_pathways, programs, failure
