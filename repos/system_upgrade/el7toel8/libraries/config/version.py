import operator
import os

import six

from leapp.exceptions import StopActorExecutionError
from leapp.libraries.stdlib import api
from leapp.models import OSReleaseFacts

OP_MAP = {
    '>': operator.gt,
    '>=': operator.ge,
    '<': operator.lt,
    '<=': operator.le
}

SUPPORTED_VERSION = {'rhel': ['7.6']}


def _version_to_tuple(version):
    """Converts the version string ``major.minor`` to ``(major, minor)`` int tuple."""
    major, minor = version.split('.')
    return (int(major), int(minor))


def _validate_versions(versions):
    """Raise ``TypeError`` if provided versions are not strings in the form ``<integer>.<integer>``."""
    for ver in versions:
        split = ver.split('.')
        if not len(split) == 2 or not all(x.isdigit() for x in split):
            raise ValueError("Versions have to be in the form of '<integer>.<integer>' "
                             "but provided was '{}'".format(versions))


def _simple_versions(versions):
    """Return ``True`` if provided versions are list of strings without comparison operators."""
    return all(len(v.split()) == 1 for v in versions)


def _cmp_versions(versions):
    """Return ``True`` if provided versions are list of strings with comparison operators."""
    split = [v.split() for v in versions]
    if not all(len(s) == 2 for s in split):
        return False

    return all(s[0] in OP_MAP for s in split)


def matches_version(match_list, detected):
    """
    Check if the `detected` version meets the criteria specified in `match_list`.

    :param match_list: specification of versions to check against
    :type match_list: list or tuple of strings in one of the two following forms:
                      ``['>'|'>='|'<'|'<='] <integer>.<integer>`` form, where elements are ANDed,
                      meaning that ``['>= 7.6', '< 7.8']`` would match for ``'7.6'``, and ``'7,7'`` only.
                      ``<integer>.<integer>`` form, where elements are ORed, meaning that
                      ``['7.6', '7.7']`` would match for ``'7.6'``, and ``'7,7'`` only.
                      These two forms cannot be mixed, otherwise ``ValueError`` is raised.
    :param detected: detected version
    :type detected: string in the form ``<integer>.<integer>``
    :return: ``True`` if `detected` value matches one of the values in `match_list`, ``False`` otherwise
    :rtype: bool
    """
    if not isinstance(match_list, (list, tuple)):
        raise TypeError("Versions to check against have to be a list or tuple "
                        "but provided was {}: '{}'".format(type(match_list), match_list))
    if not all(isinstance(e, six.string_types) for e in match_list):
        raise TypeError("Versions to check against have to be a list or tuple of strings "
                        "but provided was {}: '{}'".format([type(e) for e in match_list], match_list))
    if not isinstance(detected, six.string_types):
        raise TypeError("Detected version has to be a string "
                        "but provided was {}: '{}'".format(type(detected), detected))
    _validate_versions([detected])

    if _simple_versions(match_list):
        # match_list = ['7.6', '7.7', '7.8', '7.9']
        _validate_versions(match_list)
        return detected in match_list
    elif _cmp_versions(match_list):
        detected = _version_to_tuple(detected)
        # match_list = ['>= 7.6', '< 7.10']
        _validate_versions([s.split()[1] for s in match_list])
        for match in match_list:
            op, ver = match.split()
            ver = _version_to_tuple(ver)
            if not OP_MAP[op](detected, ver):
                return False
        return True
    else:
        raise ValueError("Versions have to be a list or tuple of strings in the form "
                         "'['>'|'>='|'<'|'<='] <integer>.<integer>' or "
                         "'<integer>.<integer>' but provided was '{}'".format(match_list))


def matches_source_version(*match_list):
    """
    Check if one of provided source versions matches the configured one.

    :param match_list: specification of versions to check against
    :type match_list: strings, for details see argument ``match_list`` of function :func:`matches_version`.
    """
    source_version = api.current_actor().configuration.version.source
    return matches_version(match_list, source_version)


def matches_target_version(*match_list):
    """
    Check if one of provided target versions matches the configured one.

    :param match_list: specification of versions to check against
    :type match_list: strings, for details see argument ``match_list`` of function :func:`matches_version`.
    """
    target_version = api.current_actor().configuration.version.target
    return matches_version(match_list, target_version)


def matches_release(allowed_releases, release):
    """Check if the given `release` is allowed to upgrade based in `allowed_releases`.

    :param allowed_releases: All supported releases
    :type allowed_releases: list or dict
    :param release: release name to be checked
    :type release: string
    :return: ``True`` if `release` value matches one of the values in `allowed_releases`, ``False`` otherwise
    :rtype: bool
    """
    if not (release and allowed_releases):
        return False

    return release in allowed_releases


def current_version():
    """Return current Linux release and version running in system.

    :raises StopActorExecutionError: this exception will be raised if no facts found to read data.
    :return: The tuple contains release name and version value.
    :rtype: (string, string)
    """
    facts_messages = api.consume(OSReleaseFacts)
    facts = next(facts_messages, None)
    if list(facts_messages):
        api.current_logger().warning('Unexpectedly received more than one OSReleaseFacts message.')
    if not facts:
        raise StopActorExecutionError(
            'Could not check OS version', details={'details': 'No OSReleaseFacts facts found.'}
        )
    return facts.release_id, facts.version_id


def is_supported_version():
    """ Verify if current system version is supported to the upgrade.

    :return: `True` if current version is supported and `False` otherwise.
    :rtype: bool
    """
    if os.getenv('LEAPP_SKIP_CHECK_OS_RELEASE'):
        return True

    release_id, version_id = current_version()

    if not matches_release(SUPPORTED_VERSION, release_id):
        return False

    return matches_version(SUPPORTED_VERSION[release_id], version_id)
