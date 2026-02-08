from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Movie(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to="movies/")
    rating = models.DecimalField(max_digits=3, decimal_places=1)
    cast = models.TextField()
    description = models.TextField(blank=True, null=True)
    trailer_url = models.URLField(blank=True, null=True)


    # 🔹 Added for Task 1 (Filters)
    genre = models.CharField(max_length=100, default="Action")
    language = models.CharField(max_length=100, default="Hindi")


    def __str__(self):
        return self.name


class Theater(models.Model):
    name = models.CharField(max_length=255)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='theaters')
    time = models.DateTimeField()

    def __str__(self):
        return f'{self.name} - {self.movie.name} at {self.time}'



class Seat(models.Model):
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.CharField(max_length=10)
    is_booked = models.BooleanField(default=False)

    # ✅ NEW FIELDS FOR TIMEOUT
    reserved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    reserved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.seat_number} in {self.theater.name}'



class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE)

    payment_status = models.CharField(max_length=20, default="PENDING")  # ⭐ matches DB
    booked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.movie.name} - {self.seat.seat_number}"



