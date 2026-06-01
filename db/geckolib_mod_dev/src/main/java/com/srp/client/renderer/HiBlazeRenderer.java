package com.srp.client.renderer;

import com.srp.client.model.HiBlazeModel;
import com.srp.entity.HiBlazeEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HiBlazeRenderer extends GeoEntityRenderer<HiBlazeEntity> {

    public HiBlazeRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HiBlazeModel());
    }
}
