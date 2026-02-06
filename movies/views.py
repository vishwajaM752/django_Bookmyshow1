from django.shortcuts import render, redirect, get_object_or_404
from .models import Movie, Theater, Seat, Booking
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY


# Movie list view
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


# Theater list view
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


# 🔥 NEW: Stripe Checkout Session
@login_required(login_url='/login/')
def create_checkout_session(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    selected_seats = request.POST.getlist('seats')

    if not selected_seats:
        return redirect('book_seats', theater_id=theater.id)

    # Store in session
    request.session['selected_seats'] = selected_seats
    request.session['theater_id'] = theater.id

    # ₹150 per seat
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
        cancel_url=request.build_absolute_uri(f'/movies/book-seats/{theater.id}/'),

    )

    return redirect(checkout_session.url, code=303)


# 🔥 NEW: Payment Success (your original booking logic here)
@login_required(login_url='/login/')
def payment_success(request):
    selected_seats = request.session.get('selected_seats')
    theater_id = request.session.get('theater_id')

    theater = get_object_or_404(Theater, id=theater_id)
    seats = Seat.objects.filter(theater=theater)

    booked_seat_numbers = []

    for seat_id in selected_seats:
        seat = get_object_or_404(Seat, id=seat_id, theater=theater)

        if not seat.is_booked:
            seat.is_booked = True
            seat.save()

            booked_seat_numbers.append(seat.seat_number)

            Booking.objects.create(
                user=request.user,
                seat=seat,
                movie=theater.movie,
                theater=theater,
                payment_status="SUCCESS" 
            )

    # 🎟️ SEND EMAIL CONFIRMATION (same as yours)
    subject = "🎟️ Your Movie Ticket Confirmation"
    message = f"""
Hi {request.user.username},

Your booking is confirmed!

🎬 Movie: {theater.movie.name}
🏢 Theater: {theater.name}
🪑 Seats: {', '.join(booked_seat_numbers)}

Enjoy your show! 🍿
"""
    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [request.user.email],
        fail_silently=False
    )

    return render(request, 'movies/booking_success.html', {
        'theater': theater,
        'seats': seats,
        'booked_seats': booked_seat_numbers
    })


# Seat booking view (ONLY REDIRECTS TO STRIPE NOW)
@login_required(login_url='/login/')
def book_seats(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    seats = Seat.objects.filter(theater=theater)

    if request.method == 'POST':
        return create_checkout_session(request, theater_id)

    return render(request, 'movies/seat_selection.html', {
        'theater': theater,
        'seats': seats
    })
