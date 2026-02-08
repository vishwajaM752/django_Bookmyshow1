from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from .models import Movie, Theater, Seat, Booking
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY


# 🎬 Movie list view
def movie_list(request):
    search_query = request.GET.get('search')
    genre = request.GET.get('genre')
    language = request.GET.get('language')

    movies = Movie.objects.all()

    if search_query:
        movies = movies.filter(name__icontains=search_query)
    if genre:
        movies = movies.filter(genre=genre)
    if language:
        movies = movies.filter(language=language)

    return render(request, 'movies/movie_list.html', {'movies': movies})


# 🎥 Theater list + trailer
def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    theaters = Theater.objects.filter(movie=movie)
    embed_url = None

    if movie.trailer_url:
        url = movie.trailer_url.strip()
        if "youtu.be/" in url:
            video_id = url.split("youtu.be/")[-1]
        elif "watch?v=" in url:
            video_id = url.split("watch?v=")[-1]
        else:
            video_id = None

        if video_id:
            video_id = video_id.split("&")[0].split("?")[0]
            embed_url = f"https://www.youtube.com/embed/{video_id}"

    return render(request, 'movies/theater_list.html', {
        'movie': movie,
        'theaters': theaters,
        'embed_url': embed_url
    })


# 💳 Stripe Checkout + seat lock
@login_required(login_url='/login/')
def create_checkout_session(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    selected_seats = request.POST.getlist('seats')

    if not selected_seats:
        return redirect('book_seats', theater_id=theater.id)

    # 🔒 Lock seats for 5 minutes
    for seat_id in selected_seats:
        seat = get_object_or_404(Seat, id=seat_id, theater=theater)

        if seat.is_booked:
            return redirect('book_seats', theater_id=theater.id)

        if seat.reserved_by and seat.reserved_by != request.user:
            if timezone.now() - seat.reserved_at < timedelta(minutes=5):
                return redirect('book_seats', theater_id=theater.id)

        seat.reserved_by = request.user
        seat.reserved_at = timezone.now()
        seat.save()

    # Save session
    request.session['selected_seats'] = selected_seats
    request.session['theater_id'] = theater.id

    amount = 150 * len(selected_seats)

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'inr',
                'product_data': {
                    'name': f"Movie Ticket - {theater.movie.name}",
                },
                'unit_amount': amount * 100,
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=request.build_absolute_uri('/movies/payment-success/'),
        cancel_url=request.build_absolute_uri(
            f'/movies/payment-cancel/{theater.id}/'
        ),
    )

    return redirect(checkout_session.url, code=303)


# ✅ Payment success → confirm booking
@login_required(login_url='/login/')
def payment_success(request):
    selected_seats = request.session.get('selected_seats')
    theater_id = request.session.get('theater_id')

    # 🔐 Safety check
    if not selected_seats or not theater_id:
        return redirect('movie_list')

    theater = get_object_or_404(Theater, id=theater_id)
    seats = Seat.objects.filter(theater=theater)

    booked_seat_numbers = []
    expired_time = timezone.now() - timedelta(minutes=5)

    for seat_id in selected_seats:
        seat = get_object_or_404(Seat, id=seat_id, theater=theater)

        if seat.is_booked:
            continue

        if (
            seat.reserved_by != request.user or
            seat.reserved_at is None or
            seat.reserved_at < expired_time
        ):
            continue

        seat.is_booked = True
        seat.reserved_by = None
        seat.reserved_at = None
        seat.save()

        booked_seat_numbers.append(seat.seat_number)

        Booking.objects.create(
            user=request.user,
            seat=seat,
            movie=theater.movie,
            theater=theater,
            payment_status="SUCCESS"
        )

    if not booked_seat_numbers:
        return redirect('book_seats', theater_id=theater.id)

    # 📧 BEAUTIFUL EMAIL CONFIRMATION
    subject = "🎟️ Movie Ticket Confirmed – Enjoy Your Show!"

    message = f"""
Hi {request.user.username},

🎉 Your movie ticket has been successfully CONFIRMED!

━━━━━━━━━━━━━━━━━━━━━━
🎬 Movie      : {theater.movie.name}
🏢 Theater    : {theater.name}
🕒 Show Time  : {theater.time}
🪑 Seats      : {', '.join(booked_seat_numbers)}
━━━━━━━━━━━━━━━━━━━━━━

Please arrive at least 15 minutes before the showtime.

Sit back, relax, grab your popcorn 🍿  
and ENJOY YOUR SHOW! 🎥✨

Thank you for booking with us.
Have a great time! 😊
"""

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [request.user.email],
        fail_silently=False
    )

    # 🧹 Clear session
    request.session.pop('selected_seats', None)
    request.session.pop('theater_id', None)

    return render(request, 'movies/booking_success.html', {
        'theater': theater,
        'seats': seats,
        'booked_seats': booked_seat_numbers
    })



# 🎫 Seat selection page
@login_required(login_url='/login/')
def book_seats(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)

    # ⏱️ Auto-release expired locks
    expired_time = timezone.now() - timedelta(minutes=5)
    Seat.objects.filter(
        theater=theater,
        is_booked=False,
        reserved_at__lt=expired_time
    ).update(reserved_by=None, reserved_at=None)

    seats = Seat.objects.filter(theater=theater)

    if request.method == 'POST':
        return create_checkout_session(request, theater_id)

    return render(request, 'movies/seat_selection.html', {
        'theater': theater,
        'seats': seats
    })


# ❌ Stripe cancel → release seats
@login_required(login_url='/login/')
def payment_cancel(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)

    Seat.objects.filter(
        theater=theater,
        reserved_by=request.user,
        is_booked=False
    ).update(reserved_by=None, reserved_at=None)

    request.session.pop('selected_seats', None)
    request.session.pop('theater_id', None)

    return redirect('book_seats', theater_id=theater.id)
