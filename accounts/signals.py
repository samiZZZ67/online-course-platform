from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import InstructorProfile, StudentProfile, User


@receiver(post_save, sender=User)
def ensure_role_profiles(sender, instance: User, **kwargs):
    if instance.role == User.Role.STUDENT:
        StudentProfile.objects.get_or_create(user=instance)
    elif instance.role == User.Role.INSTRUCTOR:
        InstructorProfile.objects.get_or_create(user=instance)
