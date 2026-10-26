"""Deterministic geography, never semantic matching or inventory inference."""
import math


def distance_meters(a_lat, a_lon, b_lat, b_lon):
    a, b = math.radians(a_lat), math.radians(b_lat)
    dlat, dlon = b-a, math.radians(b_lon-a_lon)
    h = math.sin(dlat/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def located_entity(entity, event, strong=500, moderate=1000):
    """Only explicitly verified persisted coordinates qualify as a proximity match.

    No geocoder is called, and suburb/city strings never become GPS coordinates.
    Product coordinates require a separately verified physical store relationship.
    """
    meta = entity.metadata
    report = {'entity_id': entity.entity_id, 'match': 'unlocated', 'distance_meters': None}
    if meta.get('location_verified', '').lower() != 'true' or not meta.get('location_source'):
        return report
    if entity.domain == 'shopping' and not (meta.get('location_role') == 'store' and meta.get('store_name')):
        return report
    try:
        lat, lon = float(meta['latitude']), float(meta['longitude'])
        accuracy = float(event.metadata.get('accuracy_meters', '0'))
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            return report
        distance = distance_meters(float(event.metadata['latitude']), float(event.metadata['longitude']), lat, lon)
    except (KeyError, ValueError, TypeError):
        return report
    # Uncertainty must fit wholly inside the threshold; poor GPS cannot prove proximity.
    upper = distance + accuracy
    return {**report, 'match': 'strong' if upper <= strong else 'moderate' if upper <= moderate else 'distant',
            'distance_meters': round(distance), 'accuracy_meters': accuracy,
            'location_source': meta['location_source'], 'store_name': meta.get('store_name'),
            'inventory_verified': False}
