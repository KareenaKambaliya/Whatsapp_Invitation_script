import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

class MessageQueue:
    """Persistent message queue for tracking WhatsApp message delivery status."""
    
    def __init__(self, queue_dir: str = "message_queue"):
        self.queue_dir = Path(queue_dir)
        self.pending_dir = self.queue_dir / "pending"
        self.in_progress_dir = self.queue_dir / "in_progress"
        self.failed_dir = self.queue_dir / "failed"
        self.completed_dir = self.queue_dir / "completed"
        
        # Create queue directories
        for d in [self.queue_dir, self.pending_dir, self.in_progress_dir, 
                 self.failed_dir, self.completed_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    def enqueue(self, contact_name: str, phone: str, invitation_path: str,
                message: str) -> str:
        """Add a message to the queue."""
        # Generate unique message ID using timestamp
        message_id = f"{int(time.time())}_{contact_name}"
        
        message_data = {
            "id": message_id,
            "contact_name": contact_name,
            "phone": phone,
            "invitation_path": invitation_path,
            "message": message,
            "status": "pending",
            "attempts": 0,
            "created_at": datetime.now().isoformat(),
            "last_attempt": None,
            "error": None
        }
        
        # Save to pending queue
        message_path = self.pending_dir / f"{message_id}.json"
        with open(message_path, 'w', encoding='utf-8') as f:
            json.dump(message_data, f, ensure_ascii=False, indent=2)
        
        return message_id
    
    def mark_in_progress(self, message_id: str):
        """Mark a message as being processed."""
        src = self.pending_dir / f"{message_id}.json"
        dst = self.in_progress_dir / f"{message_id}.json"
        
        if src.exists():
            with open(src) as f:
                data = json.load(f)
            data["status"] = "in_progress"
            data["last_attempt"] = datetime.now().isoformat()
            with open(dst, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            src.unlink()
    
    def mark_completed(self, message_id: str):
        """Mark a message as successfully sent."""
        src = self.in_progress_dir / f"{message_id}.json"
        dst = self.completed_dir / f"{message_id}.json"
        
        if src.exists():
            with open(src) as f:
                data = json.load(f)
            data["status"] = "completed"
            with open(dst, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            src.unlink()
    
    def mark_failed(self, message_id: str, error: str):
        """Mark a message as failed with error details."""
        src = self.in_progress_dir / f"{message_id}.json"
        dst = self.failed_dir / f"{message_id}.json"
        
        if src.exists():
            with open(src) as f:
                data = json.load(f)
            data["status"] = "failed"
            data["error"] = error
            data["attempts"] += 1
            with open(dst, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            src.unlink()
    
    def get_pending_messages(self) -> List[Dict]:
        """Get all pending messages."""
        messages = []
        for f in self.pending_dir.glob("*.json"):
            with open(f) as fp:
                messages.append(json.load(fp))
        return messages
    
    def get_failed_messages(self) -> List[Dict]:
        """Get all failed messages."""
        messages = []
        for f in self.failed_dir.glob("*.json"):
            with open(f) as fp:
                messages.append(json.load(fp))
        return messages
    
    def get_message_status(self, message_id: str) -> Optional[Dict]:
        """Get status of a specific message."""
        for d in [self.pending_dir, self.in_progress_dir, 
                 self.failed_dir, self.completed_dir]:
            path = d / f"{message_id}.json"
            if path.exists():
                with open(path) as f:
                    return json.load(f)
        return None