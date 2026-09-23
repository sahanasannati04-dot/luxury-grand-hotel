from .models import Wishlist, HotelSettings


def wishlist_count(request):
    if request.user.is_authenticated:
        count = Wishlist.objects.filter(
            user=request.user
        ).count()
    else:
        count = 0

    return {
        'wishlist_count': count
    }


def hotel_settings(request):

    hotel = HotelSettings.objects.first()

    if hotel is None:
        hotel = HotelSettings.objects.create(
            hotel_name="Luxury Grand Hotel"
        )

    return {
        'hotel_settings': hotel
    }